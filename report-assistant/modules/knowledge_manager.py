import json
import os
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from typing import Optional

from modules.config import ZHIPUAI_API_KEY, KNOWLEDGE_BASE_ID, ZHIPUAI_KB_BASE_URL, UPLOAD_MAX_SIZE

CATEGORY_LABEL_MAP = {
    "previous_report": "previous",
    "current_template": "template",
    "current_materials": "current",
    "reference_reports": "reference",
}

CATEGORY_WEIGHTS = {
    "previous_report": 3,
    "current_template": 3,
    "current_materials": 2,
    "reference_reports": 1,
}


def _get_zhipu_token() -> Optional[str]:
    if not ZHIPUAI_API_KEY:
        return None
    try:
        parts = ZHIPUAI_API_KEY.split(".")
        if len(parts) == 2:
            import base64
            payload = json.loads(base64.b64decode(parts[1] + "=="))
            return payload.get("api_key", ZHIPUAI_API_KEY)
    except Exception:
        pass
    return ZHIPUAI_API_KEY


def _build_multipart_form(fields: dict, file_path: str, file_field_name: str = "files") -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    filename = Path(file_path).name
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field_name}"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


def _zhipu_request_json(method: str, path: str, data: Optional[dict] = None,
                         base_url: Optional[str] = None) -> dict:
    token = _get_zhipu_token()
    if not token:
        return {"success": False, "error": "ZHIPUAI_API_KEY 未配置"}
    url_base = base_url or ZHIPUAI_KB_BASE_URL
    url = f"{url_base.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "data": result}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _zhipu_upload_file(kb_id: str, file_path: str, knowledge_type: int = 1) -> dict:
    token = _get_zhipu_token()
    if not token:
        return {"success": False, "error": "ZHIPUAI_API_KEY 未配置"}
    url = f"{ZHIPUAI_KB_BASE_URL.rstrip('/')}/open/document/upload_document/{kb_id}"
    body_bytes, content_type = _build_multipart_form(
        {"knowledge_type": str(knowledge_type)}, file_path, file_field_name="files"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "data": result}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _list_kb_documents(kb_id: str, page: int = 1, size: int = 50) -> dict:
    path = f"open/document?knowledge_id={kb_id}&page={page}&size={size}"
    return _zhipu_request_json("GET", path)


def _delete_kb_document(doc_id: str) -> dict:
    path = f"open/document/{doc_id}"
    return _zhipu_request_json("DELETE", path)


def _retrieve_knowledge(kb_id: str, query: str, document_ids: list, top_k: int = 3) -> dict:
    body = {
        "query": query,
        "knowledge_ids": [kb_id],
        "document_ids": document_ids,
        "top_k": top_k,
        "recall_method": "mixed",
        "rerank_status": 1,
        "rerank_model": "rerank",
    }
    return _zhipu_request_json("POST", "open/knowledge/retrieve", data=body)


def _get_document_detail(doc_id: str) -> dict:
    path = f"open/document/{doc_id}"
    return _zhipu_request_json("GET", path)


def _reembedding_document(doc_id: str) -> dict:
    path = f"open/document/embedding/{doc_id}"
    return _zhipu_request_json("POST", path, data={})


def get_embedding_status(doc_id: str) -> dict:
    resp = _get_document_detail(doc_id)
    if not resp["success"]:
        return {"success": False, "error": resp.get("error", "查询失败")}

    raw_data = resp.get("data", {})
    doc_data = raw_data.get("data", {}) if isinstance(raw_data, dict) else {}
    if not doc_data:
        doc_data = raw_data

    embedding_stat = doc_data.get("embedding_stat", -1)
    fail_info = doc_data.get("failInfo") or {}

    status_map = {0: "处理中", 1: "处理中", 2: "已完成"}
    status_text = status_map.get(embedding_stat, f"未知({embedding_stat})")

    if isinstance(fail_info, dict) and fail_info.get("embedding_code"):
        return {
            "success": True,
            "status": "failed",
            "status_text": "向量化失败",
            "fail_reason": fail_info.get("embedding_msg", "未知错误"),
            "fail_code": fail_info.get("embedding_code"),
            "embedding_stat": embedding_stat,
            "doc_id": doc_id,
        }

    if embedding_stat == 2:
        return {
            "success": True,
            "status": "completed",
            "status_text": "✅ 向量化完成",
            "embedding_stat": embedding_stat,
            "doc_id": doc_id,
        }

    return {
        "success": True,
        "status": "processing",
        "status_text": f"⏳ 向量化{status_text}",
        "embedding_stat": embedding_stat,
        "doc_id": doc_id,
    }


def reembed_document(doc_id: str) -> dict:
    resp = _reembedding_document(doc_id)
    if resp["success"]:
        code = resp.get("data", {}).get("code", -1)
        if code == 200:
            return {"success": True, "message": "重新向量化请求已提交"}
    return {"success": False, "error": resp.get("error", resp.get("data", {}).get("message", "请求失败"))}


def upload_to_knowledge(file_path: str, category_label: str, project_id: int) -> dict:
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    file_size = file_path_obj.stat().st_size
    if file_size > UPLOAD_MAX_SIZE:
        return {"success": False, "error": f"文件大小({file_size / 1024 / 1024:.1f}MB)超过10MB限制"}

    kb_id = KNOWLEDGE_BASE_ID
    if not kb_id:
        return {"success": False, "error": "KNOWLEDGE_BASE_ID 未配置"}

    prefix = f"proj_{project_id}_"
    prefixed_name = f"{prefix}{category_label}_{file_path_obj.name}"
    import shutil
    temp_path = file_path_obj.with_name(prefixed_name)
    shutil.copy2(str(file_path_obj), str(temp_path))

    try:
        result = _zhipu_upload_file(kb_id, str(temp_path), knowledge_type=1)
        if result["success"]:
            data = result.get("data", {})
            success_infos = data.get("data", {}).get("successInfos", [])
            if success_infos and isinstance(success_infos, list):
                doc_id = success_infos[0].get("documentId", "")
                doc_name = success_infos[0].get("fileName", prefixed_name)
            else:
                doc_id = data.get("data", {}).get("id", "")
                doc_name = prefixed_name

            kb_status = {"status": "uploaded", "doc_id": doc_id}
            if doc_id:
                emb_status = get_embedding_status(doc_id)
                kb_status = {
                    "status": emb_status.get("status", "unknown"),
                    "status_text": emb_status.get("status_text", ""),
                    "doc_id": doc_id,
                    "fail_reason": emb_status.get("fail_reason", ""),
                    "fail_code": emb_status.get("fail_code", ""),
                }

            return {
                "success": True,
                "file_id": doc_id,
                "filename": doc_name,
                "kb_status": kb_status,
            }
        return result
    finally:
        if temp_path.exists():
            temp_path.unlink()


def delete_project_files(project_id: int) -> list[dict]:
    results = []
    kb_id = KNOWLEDGE_BASE_ID
    if not kb_id:
        return results

    prefix = f"proj_{project_id}_"

    all_deleted = []
    page = 1
    while True:
        list_resp = _list_kb_documents(kb_id, page=page, size=50)
        if not list_resp["success"]:
            break

        raw_data = list_resp.get("data", {})
        doc_list = raw_data.get("data", {}).get("list", []) if isinstance(raw_data, dict) else []
        if not doc_list:
            break

        total = raw_data.get("data", {}).get("total", 0) if isinstance(raw_data, dict) else 0

        for doc in doc_list:
            doc_name = doc.get("name", "")
            doc_id = doc.get("id", "")
            if doc_name.startswith(prefix) and doc_id:
                del_resp = _delete_kb_document(doc_id)
                results.append({
                    "file": doc_name,
                    "success": del_resp["success"],
                    "error": del_resp.get("error"),
                })

        if page * 50 >= total:
            break
        page += 1

    return results


def check_template_status(project_id: int) -> dict:
    from modules.project import get_files

    files = get_files(project_id)
    has_template = any(f["category"] == "current_template" for f in files)
    has_previous = any(f["category"] == "previous_report" for f in files)

    return {
        "has_template": has_template,
        "has_previous": has_previous,
        "can_generate": has_template or has_previous,
        "message": (
            None
            if has_template
            else ("上期报告可用，可从报告中提取章节结构" if has_previous else "请上传本期报告模板或上期报告")
        ),
    }


def search_knowledge(project_id: int, query: str, top_k: int = 10) -> dict:
    from modules.project import get_files

    files = get_files(project_id)
    if not files:
        return {"success": True, "items": [], "total": 0}

    scored = []
    for f in files:
        weight = CATEGORY_WEIGHTS.get(f["category"], 1)
        scored.append((weight, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_files = scored[:top_k]

    kb_id = KNOWLEDGE_BASE_ID
    if not kb_id:
        return {"success": False, "error": "KNOWLEDGE_BASE_ID 未配置", "items": [], "total": 0}

    token = _get_zhipu_token()
    if not token:
        return {"success": False, "error": "ZHIPUAI_API_KEY 未配置", "items": [], "total": 0}

    items = []
    for weight, f in top_files:
        filename = f["filename"]
        category_weight = CATEGORY_WEIGHTS.get(f["category"], 1)

        retrieve_resp = _retrieve_knowledge(kb_id, query, document_ids=[], top_k=3)
        if retrieve_resp["success"]:
            raw_data = retrieve_resp.get("data", {})
            chunks = raw_data.get("data", []) if isinstance(raw_data, dict) else []
            if not isinstance(chunks, list):
                chunks = [chunks] if chunks else []

            for chunk in chunks:
                if isinstance(chunk, dict):
                    chunk_text = chunk.get("text", "")
                    metadata = chunk.get("metadata", {})
                    chunk_doc_name = metadata.get("doc_name", "")
                elif isinstance(chunk, str):
                    chunk_text = chunk
                    chunk_doc_name = ""
                else:
                    continue
                if chunk_text:
                    items.append({
                        "content": chunk_text[:500],
                        "filename": chunk_doc_name or filename,
                        "category": f["category"],
                        "weight": category_weight,
                        "source_label": "🏷️知识库",
                    })

    return {"success": True, "items": items, "total": len(items)}
