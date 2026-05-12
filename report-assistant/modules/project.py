import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from modules.config import DB_PATH, UPLOAD_DIR, EXPORT_DIR
from modules.knowledge_manager import delete_project_files


def get_conn():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed')),
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            sources TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('preference', 'format', 'pitfall', 'knowledge')),
            keywords TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS project_config (
            project_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL DEFAULT 'Flash',
            mode TEXT NOT NULL DEFAULT '问答',
            web_search INTEGER NOT NULL DEFAULT 1,
            sections TEXT DEFAULT '[]',
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
    """)
    conn.commit()

    cur = conn.execute("PRAGMA table_info(projects)")
    cols = {r["name"] for r in cur.fetchall()}
    if "company" in cols and "name" in cols:
        conn.execute("UPDATE projects SET name = company WHERE name IS NULL OR name = ''")
    if "completed_at" not in cols:
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN completed_at TEXT")
        except sqlite3.OperationalError:
            pass
    if "export_path" not in cols:
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN export_path TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    if "export_filename" not in cols:
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN export_filename TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

    cur4 = conn.execute("PRAGMA table_info(files)")
    file_cols = {r["name"] for r in cur4.fetchall()}
    if "kb_doc_id" not in file_cols:
        try:
            conn.execute("ALTER TABLE files ADD COLUMN kb_doc_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    if "kb_status" not in file_cols:
        try:
            conn.execute("ALTER TABLE files ADD COLUMN kb_status TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

    cur2 = conn.execute("PRAGMA table_info(messages)")
    msg_cols = {r["name"] for r in cur2.fetchall()}
    if "sources" not in msg_cols:
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN sources TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass

    cur3 = conn.execute("PRAGMA table_info(memories)")
    mem_cols = {r["name"] for r in cur3.fetchall()}
    if "project_id" in mem_cols:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript("""
            CREATE TABLE memories_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'knowledge' CHECK(type IN ('preference', 'format', 'pitfall', 'knowledge')),
                keywords TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO memories_new (id, content, created_at, updated_at)
                SELECT id, content, created_at, updated_at FROM memories;
            DROP TABLE memories;
            ALTER TABLE memories_new RENAME TO memories;
        """)
        conn.execute("PRAGMA foreign_keys=ON")

    conn.commit()
    conn.close()


# ───────────────────── 项目管理 ─────────────────────

def create_project(name: str) -> int:
    conn = get_conn()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO projects (name, status, created_at) VALUES (?, 'active', ?)",
        [name.strip(), now],
    )
    project_id = cursor.lastrowid
    conn.execute("INSERT INTO project_config (project_id) VALUES (?)", [project_id])

    init_tags = [
        ("preference", "风格偏好", f"项目「{name}」的风格偏好记录"),
        ("format", "格式规范", f"项目「{name}」的格式规范要求"),
        ("knowledge", "项目背景", f"项目「{name}」的基本背景信息"),
    ]
    now2 = datetime.now().isoformat()
    for t, kw, ct in init_tags:
        conn.execute(
            "INSERT INTO memories (type, keywords, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            [t, kw, ct, now2, now2],
        )

    conn.commit()
    conn.close()
    return project_id


def list_active_projects():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_completed_projects():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM projects WHERE status = 'completed' ORDER BY completed_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", [project_id]
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def complete_project(project_id: int) -> dict:
    summary = {"project_id": project_id, "files_deleted": 0, "messages_cleared": 0, "zhipu_results": []}

    zhipu_results = delete_project_files(project_id)
    summary["zhipu_results"] = zhipu_results

    project_dir = UPLOAD_DIR / str(project_id)
    if project_dir.exists():
        files_count = sum(1 for _ in project_dir.rglob("*") if _.is_file())
        shutil.rmtree(project_dir)
        summary["files_deleted"] = files_count

    conn = get_conn()
    cur = conn.execute("DELETE FROM messages WHERE project_id = ?", [project_id])
    summary["messages_cleared"] = cur.rowcount

    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE projects SET status = 'completed', completed_at = ? WHERE id = ?",
        [now, project_id],
    )
    conn.commit()
    conn.close()

    return summary


# ───────────────────── 对话管理 ─────────────────────

def save_message(project_id: int, role: str, content: str, sources: Optional[list] = None) -> dict:
    now = datetime.now().isoformat()
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO messages (project_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?)",
        [project_id, role, content, sources_json, now],
    )
    msg_id = cursor.lastrowid
    conn.execute("UPDATE projects SET completed_at = completed_at WHERE id = ?", [project_id])
    conn.commit()
    conn.close()
    return {"id": msg_id, "project_id": project_id, "role": role, "content": content, "sources": sources_json,
            "created_at": now}


def get_conversation(project_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE project_id = ? ORDER BY created_at ASC",
        [project_id],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ───────────────────── 向后兼容包装 ─────────────────────

def get_messages(project_id: int) -> list[dict]:
    return get_conversation(project_id)


def add_message(project_id: int, role: str, content: str, sources: Optional[list] = None):
    save_message(project_id, role, content, sources=sources)


def get_active_projects():
    return list_active_projects()


def get_completed_projects():
    return list_completed_projects()


# ───────────────────── 文件管理 ─────────────────────

def add_file(project_id: int, category: str, filename: str, filepath: str,
             kb_doc_id: str = "", kb_status: str = ""):
    now = datetime.now().isoformat()
    kb_status_json = json.dumps(kb_status, ensure_ascii=False) if isinstance(kb_status, dict) else (kb_status or "")
    conn = get_conn()
    conn.execute(
        "INSERT INTO files (project_id, category, filename, filepath, kb_doc_id, kb_status, uploaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [project_id, category, filename, filepath, kb_doc_id, kb_status_json, now],
    )
    conn.commit()
    conn.close()


def update_file_kb_status(file_id: int, kb_doc_id: str = "", kb_status: dict = None):
    conn = get_conn()
    if kb_status is not None:
        kb_status_json = json.dumps(kb_status, ensure_ascii=False)
        conn.execute(
            "UPDATE files SET kb_doc_id = ?, kb_status = ? WHERE id = ?",
            [kb_doc_id, kb_status_json, file_id],
        )
    elif kb_doc_id:
        conn.execute(
            "UPDATE files SET kb_doc_id = ? WHERE id = ?",
            [kb_doc_id, file_id],
        )
    conn.commit()
    conn.close()


def get_files(project_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM files WHERE project_id = ? ORDER BY uploaded_at DESC",
        [project_id],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ───────────────────── 记忆管理 ─────────────────────

MEMORY_TYPES = ["preference", "format", "pitfall", "knowledge"]
MEMORY_TYPE_LABELS = {"preference": "风格偏好", "format": "格式规范", "pitfall": "常见陷阱", "knowledge": "领域知识"}


def add_memory(mtype: str, keywords: str, content: str) -> int:
    now = datetime.now().isoformat()
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO memories (type, keywords, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        [mtype, keywords, content, now, now],
    )
    memory_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return memory_id


def update_memory(memory_id: int, mtype: str, keywords: str, content: str):
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "UPDATE memories SET type = ?, keywords = ?, content = ?, updated_at = ? WHERE id = ?",
        [mtype, keywords, content, now, memory_id],
    )
    conn.commit()
    conn.close()


def delete_memory(memory_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM memories WHERE id = ?", [memory_id])
    conn.commit()
    conn.close()


def get_memories(mtype: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
    conn = get_conn()
    conditions = []
    params = []
    if mtype and mtype in MEMORY_TYPES:
        conditions.append("type = ?")
        params.append(mtype)
    if search:
        conditions.append("(keywords LIKE ? OR content LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM memories {where} ORDER BY updated_at DESC",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_memories(search: str) -> list[dict]:
    return get_memories(search=search)


# ───────────────────── 章节管理（报告模式） ─────────────────────

def set_export_path(project_id: int, export_path: str, export_filename: str):
    conn = get_conn()
    conn.execute(
        "UPDATE projects SET export_path = ?, export_filename = ? WHERE id = ?",
        [export_path, export_filename, project_id],
    )
    conn.commit()
    conn.close()


def get_sections(project_id: int) -> list:
    config = get_project_config(project_id)
    raw = config.get("sections", "[]")
    try:
        sections = json.loads(raw) if isinstance(raw, str) else raw
        return sections if isinstance(sections, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def update_section(project_id: int, index: int, **kwargs):
    sections = get_sections(project_id)
    if 0 <= index < len(sections):
        sections[index].update(kwargs)
        update_project_config(project_id, sections=json.dumps(sections, ensure_ascii=False))


def confirm_section(project_id: int, index: int, content: str):
    update_section(project_id, index, confirmed=True, content=content)


def get_current_section(project_id: int) -> Optional[dict]:
    sections = get_sections(project_id)
    for i, s in enumerate(sections):
        if not s.get("confirmed"):
            s["_index"] = i
            return s
    return None


def get_section_progress(project_id: int) -> dict:
    sections = get_sections(project_id)
    total = len(sections)
    confirmed = sum(1 for s in sections if s.get("confirmed"))
    return {"total": total, "confirmed": confirmed, "remaining": total - confirmed}


def get_export_info(project_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT export_path, export_filename FROM projects WHERE id = ?", [project_id]
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["has_export"] = bool(result.get("export_path"))
        return result
    return {"export_path": "", "export_filename": "", "has_export": False}


# ───────────────────── 项目配置 ─────────────────────

def get_project_config(project_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM project_config WHERE project_id = ?", [project_id]
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["web_search"] = bool(result["web_search"])
        return result
    return {"model": "Flash", "mode": "问答", "web_search": True, "sections": "[]"}


def update_project_config(project_id: int, **kwargs):
    allowed = {"model", "mode", "web_search", "sections"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]
    conn = get_conn()
    conn.execute(
        f"UPDATE project_config SET {set_clause} WHERE project_id = ?",
        values,
    )
    conn.commit()
    conn.close()
