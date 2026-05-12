import json
import re
import urllib.request
import urllib.error
from typing import Optional, Generator

from modules.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from modules.project import (
    get_conversation, get_memories, add_memory,
    get_files, get_project_config, update_project_config,
)
from modules.knowledge_manager import CATEGORY_LABEL_MAP, search_knowledge
from modules.search_manager import search_and_format


MODEL_MAP = {
    "Flash": "deepseek-v4-flash",
    "Pro": "deepseek-v4-pro",
}


SYSTEM_PROMPT_BASE = (
    "你是一位银行授信审批专家，正在撰写一份尽责调查报告。\n"
    "回答必须基于提供的资料，引用来源。如果资料不足，明确告知缺失部分。\n"
    "引用格式：使用标注符号标注信息来源，如 [🏷️知识库]、[🌐网络]、[🧠模型知识]。\n"
    "保持专业、客观、严谨的文风。"
)


def _strip_html_for_api(text: str) -> str:
    text = re.sub(r'<details[^>]*>.*?</details>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _deepseek_stream(api_key: str, base_url: str, messages: list, model: str,
                     thinking: bool = False) -> Generator[dict, None, None]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 8192 if thinking else 4096,
    }
    if thinking:
        payload["thinking"] = {"type": "enabled"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line_raw in resp:
                if not line_raw:
                    break
                line = line_raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                content = line[5:].strip()
                if not content or content == "[DONE]":
                    continue
                try:
                    parsed = json.loads(content)
                    delta = parsed.get("choices", [{}])[0].get("delta", {})
                    reasoning = delta.get("reasoning_content", "")
                    content_text = delta.get("content", "")
                    if reasoning:
                        yield {"type": "reasoning", "text": reasoning}
                    if content_text:
                        yield {"type": "content", "text": content_text}
                except json.JSONDecodeError:
                    pass
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        yield {"type": "error", "text": f"\n\n**API错误** (HTTP {e.code}): {error_body}"}
    except Exception as e:
        yield {"type": "error", "text": f"\n\n**请求失败**: {str(e)}"}


def _build_context(project_id: int, query: str, mode: str, web_search_enabled: bool) -> dict:
    memories = get_memories()
    knowledge_items = search_knowledge(project_id, query, top_k=10).get("items", [])

    search_result = None
    if web_search_enabled:
        search_result = search_and_format(query, use_extract=False)

    config = get_project_config(project_id)
    sections_raw = config.get("sections", "[]")

    memory_block = ""
    if memories:
        mem_lines = ["## 📋 记忆库（历史经验）"]
        for m in memories[:10]:
            memory_block += f"- [{m['type']}] {m['keywords']}: {m['content'][:200]}\n"
        memory_block = "\n".join(mem_lines) + "\n" + memory_block

    kb_block = ""
    if knowledge_items:
        kb_lines = ["## 📚 知识库资料（按权重排序）"]
        for item in knowledge_items:
            cat_label = CATEGORY_LABEL_MAP.get(item["category"], item["category"])
            kb_block += f"[权重×{item['weight']}] [{cat_label}] {item['content']}\n"
        kb_block = "\n".join(kb_lines) + "\n" + kb_block

    search_block = ""
    if search_result and search_result["success"] and search_result["total_count"] > 0:
        search_block = "## 🌐 联网搜索结果\n" + search_result["formatted"]

    sections_block = ""
    if mode == "报告":
        try:
            sections = json.loads(sections_raw) if isinstance(sections_raw, str) else sections_raw
            if sections:
                sections_block = "## 📋 报告章节结构\n当前章节列表：\n"
                for i, s in enumerate(sections, 1):
                    status_mark = "✅" if s.get("confirmed") else "⏳"
                    sections_block += f"{i}. {status_mark} {s.get('title', s.get('name', ''))}\n"
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "memory_block": memory_block,
        "kb_block": kb_block,
        "search_block": search_block,
        "sections_block": sections_block,
    }


def _build_messages(project_id: int, query: str, mode: str, web_search_enabled: bool) -> list:
    context = _build_context(project_id, query, mode, web_search_enabled)

    context_parts = []
    if context["memory_block"]:
        context_parts.append(context["memory_block"])
    if context["kb_block"]:
        context_parts.append(context["kb_block"])
    if context["search_block"]:
        context_parts.append(context["search_block"])
    if context["sections_block"]:
        context_parts.append(context["sections_block"])

    context_str = "\n\n".join(context_parts) if context_parts else "暂无外部资料。"

    system_content = SYSTEM_PROMPT_BASE + f"\n\n## 参考资料\n{context_str}"

    if mode == "报告":
        system_content += (
            "\n\n## 报告模式要求\n"
            "你正在逐章撰写尽责调查报告。请严格按照当前章节的主题进行撰写。\n"
            "每章应包含：章节标题、正文内容、必要的分析和结论。\n"
            "如果当前章节需要数据支撑，引用提供的资料并标注来源。"
        )

    messages = [{"role": "system", "content": system_content}]

    conversation = get_conversation(project_id)
    recent = conversation[-20:] if len(conversation) > 20 else conversation
    for msg in recent:
        content = _strip_html_for_api(msg["content"]) if msg["role"] == "assistant" else msg["content"]
        messages.append({"role": msg["role"], "content": content})

    messages.append({"role": "user", "content": query})

    return messages, context


def _auto_learn(project_id: int, query: str, response: str):
    learn_prompt = (
        f"分析以下对话，提取本次对话中发现的新的写作偏好、格式要求或注意事项：\n\n"
        f"用户问题：{query}\n\n"
        f"助手回答：{response}\n\n"
        f"如果有新的经验教训需要记录，请按以下格式返回，每行一条：\n"
        f"TYPE: knowledge|preference|format|pitfall\n"
        f"KEYWORDS: 关键词（逗号分隔）\n"
        f"CONTENT: 具体内容\n"
        f"如果没有需要记录的内容，请返回：NONE"
    )

    msgs = [
        {"role": "system", "content": "你是一个经验提取助手。分析对话，提取有价值的经验教训。"},
        {"role": "user", "content": learn_prompt},
    ]

    api_key = DEEPSEEK_API_KEY
    if not api_key:
        return

    full_response = ""
    for chunk in _deepseek_stream(api_key, DEEPSEEK_BASE_URL, msgs, "deepseek-v4-flash"):
        if chunk["type"] == "content":
            full_response += chunk["text"]

    if "NONE" in full_response.strip():
        return

    lines = full_response.strip().split("\n")
    entry = {}
    for line in lines:
        if line.startswith("TYPE:"):
            entry["type"] = line[5:].strip().lower()
        elif line.startswith("KEYWORDS:"):
            entry["keywords"] = line[9:].strip()
        elif line.startswith("CONTENT:"):
            entry["content"] = line[8:].strip()

    if entry.get("type") and entry.get("content"):
        add_memory(
            entry["type"] if entry["type"] in ("preference", "format", "pitfall", "knowledge") else "knowledge",
            entry.get("keywords", ""),
            entry["content"],
        )


def chat(project_id: int, query: str, model: str, mode: str, web_search_enabled: bool) -> Generator[dict, None, None]:
    api_key = DEEPSEEK_API_KEY
    if not api_key:
        yield {"type": "error", "text": "**❌ DEEPSEEK_API_KEY 未配置**\n\n请在 .env 文件中设置 DEEPSEEK_API_KEY。"}
        return

    deepseek_model = MODEL_MAP.get(model, "deepseek-v4-flash")

    messages, context = _build_messages(project_id, query, mode, web_search_enabled)

    full_response = ""
    try:
        for chunk in _deepseek_stream(api_key, DEEPSEEK_BASE_URL, messages, deepseek_model, thinking=True):
            if chunk["type"] == "content":
                full_response += chunk["text"]
            elif chunk["type"] == "error":
                full_response += chunk["text"]
            yield chunk
    except Exception as e:
        yield {"type": "error", "text": f"\n\n**生成失败**: {str(e)}"}
        return

    try:
        _auto_learn(project_id, query, full_response)
    except Exception:
        pass


def extract_sections(project_id: int, query: Optional[str] = None) -> list:
    from modules.project import get_files, update_project_config

    files = get_files(project_id)
    template_files = [f for f in files if f["category"] == "current_template"]
    previous_files = [f for f in files if f["category"] == "previous_report"]

    source_desc = ""
    if template_files:
        source_desc = f"使用本期模板文件：{template_files[0]['filename']}"
    elif previous_files:
        source_desc = f"使用上期报告文件：{previous_files[0]['filename']}"

    prompt = (
        f"你是一位银行授信审批专家。请为一尽责调查报告提取章节结构。\n"
        f"{source_desc}\n"
        f"请严格按JSON数组格式返回，每个元素包含 title 和 description 字段：\n"
        f'[{{"title": "第一章标题", "description": "本章内容概述"}}, ...]\n'
        f"只返回JSON数组，不要有其他文字。"
    )

    api_key = DEEPSEEK_API_KEY
    if not api_key:
        return _default_sections()

    msgs = [
        {"role": "system", "content": "你是一个尽责调查报告章节提取专家。"},
        {"role": "user", "content": prompt},
    ]

    full_response = ""
    for chunk in _deepseek_stream(api_key, DEEPSEEK_BASE_URL, msgs, "deepseek-v4-flash"):
        if chunk["type"] == "content":
            full_response += chunk["text"]

    try:
        sections = json.loads(full_response.strip())
        if isinstance(sections, list) and len(sections) > 0:
            for s in sections:
                s["confirmed"] = False
            update_project_config(project_id, sections=json.dumps(sections, ensure_ascii=False))
            return sections
    except (json.JSONDecodeError, TypeError):
        pass

    sections = _default_sections()
    update_project_config(project_id, sections=json.dumps(sections, ensure_ascii=False))
    return sections


def _default_sections() -> list:
    return [
        {"title": "一、授信申请人基本情况", "description": "申请人基本信息、股权结构、经营资质等", "confirmed": False},
        {"title": "二、经营财务状况分析", "description": "资产负债、营收利润、现金流等财务指标分析", "confirmed": False},
        {"title": "三、行业与市场环境分析", "description": "行业现状、竞争格局、政策环境等", "confirmed": False},
        {"title": "四、贷款用途及还款来源分析", "description": "资金用途合理性、还款来源可靠性", "confirmed": False},
        {"title": "五、担保措施分析", "description": "抵质押物、保证人、担保方案等", "confirmed": False},
        {"title": "六、风险提示与缓释措施", "description": "主要风险点及应对措施", "confirmed": False},
        {"title": "七、综合评估与授信建议", "description": "综合评分、授信额度、条件建议", "confirmed": False},
    ]
