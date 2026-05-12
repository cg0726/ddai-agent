import json
import os
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from typing import Optional

from modules.config import ZHIPUAI_API_KEY, KNOWLEDGE_BASE_ID, ZHIPUAI_BASE_URL, UPLOAD_MAX_SIZE

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


def _build_multipart_form(fields: dict, file_path: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    filename = Path(file_path).name
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(f"\r\n".encode("utf-8"))
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


def _zhipu_request_json(method: str, path: str, data: Optional[dict] = None) -> dict:
    token = _get_zhipu_token()
    if not token:
        return {"success": False, "error": "ZHIPUAI_API_KEY 未配置"}
    url = f"{ZHIPUAI_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
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


def _zhipu_upload_file(kb_id: str, file_path: str) -> dict:
    token = _get_zhipu_token()
    if not token:
        return {"success": False, "error": "ZHIPUAI_API_KEY 未配置"}
    url = f"{ZHIPUAI_BASE_URL.rstrip('/')}/knowledge/{kb_id}/files"
    body_bytes, content_type = _build_multipart_form({"purpose": "file"}, file_path)
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
    temp_path = file_path_obj.with_name(prefixed_name)
    import shutil
    shutil.copy2(str(file_path_obj), str(temp_path))

    try:
        result = _zhipu_upload_file(kb_id, str(temp_path))
        if result["success"]:
            data = result.get("data", {})
            file_id = ""
            if isinstance(data, dict):
                file_id = data.get("id", data.get("file_id", data.get("data", {}).get("id", "")))
            elif isinstance(data, str):
                file_id = data
            return {
                "success": True,
                "file_id": file_id,
                "filename": prefixed_name,
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
    list_resp = _zhipu_request_json("GET", f"knowledge/{kb_id}/files")
    if not list_resp["success"]:
        return results

    data = list_resp.get("data", {})
    if isinstance(data, dict):
        file_list = data.get("data", [])
    elif isinstance(data, list):
        file_list = data
    else:
        file_list = []

    if not isinstance(file_list, list):
        file_list = [file_list]

    for f in file_list:
        fname = f.get("filename", f.get("file_name", ""))
        fid = f.get("id", f.get("file_id", ""))
        if fname.startswith(prefix) and fid:
            del_resp = _zhipu_request_json("DELETE", f"knowledge/{kb_id}/files/{fid}")
            results.append({
                "file": fname,
                "success": del_resp["success"],
                "error": del_resp.get("error"),
            })

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
        retrieve_resp = _zhipu_request_json(
            "POST",
            f"knowledge/{kb_id}/retrieve",
            {"query": query, "filename": filename, "top_k": 3},
        )
        if retrieve_resp["success"]:
            data = retrieve_resp.get("data", {})
            chunks = []
            if isinstance(data, dict):
                chunks = data.get("chunks", data.get("data", []))
                if isinstance(chunks, dict):
                    chunks = [chunks]
            elif isinstance(data, list):
                chunks = data
            if not isinstance(chunks, list):
                chunks = [chunks] if chunks else []

            for chunk in chunks:
                if isinstance(chunk, dict):
                    chunk_text = chunk.get("content", chunk.get("text", ""))
                elif isinstance(chunk, str):
                    chunk_text = chunk
                else:
                    chunk_text = str(chunk)
                if chunk_text:
                    items.append({
                        "content": chunk_text[:500],
                        "filename": filename,
                        "category": f["category"],
                        "weight": category_weight,
                        "source_label": "🏷️知识库",
                    })

    return {"success": True, "items": items, "total": len(items)}
