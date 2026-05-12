import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

from modules.config import (
    ZHIHU_ACCESS_SECRET,
    EXTRACT_MODEL,
    EXTRACT_API_KEY,
    EXTRACT_BASE_URL,
    DEEPSEEK_API_KEY,
)


def _zhihu_request(path: str, query: str) -> dict:
    if not ZHIHU_ACCESS_SECRET:
        return {"success": False, "error": "ZHIHU_ACCESS_SECRET 未配置", "items": []}

    url = f"https://developer.zhihu.com/api/v1/content/{path}"
    params = json.dumps({"query": query, "limit": 5}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZHIHU_ACCESS_SECRET}",
        "User-Agent": "Mozilla/5.0",
    }
    req = urllib.request.Request(url, data=params, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            items = result.get("data", result.get("items", []))
            if not isinstance(items, list):
                items = [items] if items else []
            return {"success": True, "items": items[:5]}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}: {error_body}", "items": []}
    except Exception as e:
        return {"success": False, "error": str(e), "items": []}


def search_zhihu(query: str) -> dict:
    result = _zhihu_request("zhihu_search", query)
    if not result["success"]:
        return result
    items = []
    for item in result["items"]:
        items.append({
            "title": item.get("title", item.get("question", "")),
            "snippet": _clean_html(item.get("snippet", item.get("content", ""))),
            "url": item.get("url", item.get("link", "")),
            "source": "知乎",
            "type": "zhihu",
            "recency": item.get("updated_time", item.get("created_time", "")),
        })
    return {"success": True, "items": items[:5]}


def search_web(query: str) -> dict:
    result = _zhihu_request("global_search", query)
    if not result["success"]:
        return result
    items = []
    for item in result["items"]:
        items.append({
            "title": item.get("title", ""),
            "snippet": _clean_html(item.get("snippet", item.get("content", ""))),
            "url": item.get("url", item.get("link", "")),
            "source": item.get("source", "全网"),
            "type": "web",
            "recency": item.get("updated_time", item.get("created_time", "")),
        })
    return {"success": True, "items": items[:5]}


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def _call_extract_model(url: str) -> Optional[str]:
    api_key = EXTRACT_API_KEY or DEEPSEEK_API_KEY
    model = EXTRACT_MODEL or "deepseek-v4-flash"
    base_url = EXTRACT_BASE_URL or "https://api.deepseek.com"

    if not api_key:
        return None

    prompt = f"请提取以下网页的正文内容，去除导航、广告等无关信息，返回精简摘要：\n\n{url}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个网页内容提取助手。请提取指定URL的正文内容，返回简洁的摘要。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else None
    except Exception:
        return None


def search_and_format(query: str, use_extract: bool = False) -> dict:
    zhihu_results = search_zhihu(query)
    web_results = search_web(query)

    combined = []
    sources_meta = []

    for item in zhihu_results.get("items", []):
        enriched = dict(item)
        enriched["weight"] = 0.5
        enriched["weight_label"] = "×0.5（站内）"
        if use_extract and item.get("url"):
            extracted = _call_extract_model(item["url"])
            if extracted:
                enriched["extracted"] = extracted
        combined.append(enriched)
        sources_meta.append({
            "title": item["title"],
            "source": item["source"],
            "type": "zhihu",
            "weight": 0.5,
        })

    for item in web_results.get("items", []):
        enriched = dict(item)
        enriched["weight"] = 1.0
        enriched["weight_label"] = "×1.0（全网）"
        if use_extract and item.get("url"):
            extracted = _call_extract_model(item["url"])
            if extracted:
                enriched["extracted"] = extracted
        combined.append(enriched)
        sources_meta.append({
            "title": item["title"],
            "source": item["source"],
            "type": "web",
            "weight": 1.0,
        })

    formatted_lines = []
    for i, item in enumerate(combined, 1):
        recency_str = item.get("recency", "")
        if recency_str and recency_str != "0":
            try:
                dt = datetime.fromisoformat(str(recency_str).replace("Z", "+00:00"))
                recency_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                recency_str = str(recency_str) if recency_str else "未知"
        else:
            recency_str = "未知"

        content = item.get("extracted", item.get("snippet", "无摘要"))
        formatted_lines.append(
            f"[{i}] {item['title']}\n"
            f"    来源: {item['source']} | 时效: {recency_str} | 权重: {item['weight_label']}\n"
            f"    摘要: {content}\n"
        )

    return {
        "success": True,
        "query": query,
        "results": combined,
        "sources_meta": sources_meta,
        "formatted": "\n".join(formatted_lines),
        "total_count": len(combined),
    }
