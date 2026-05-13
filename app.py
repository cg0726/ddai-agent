import streamlit as st

st.set_page_config(page_title="尽责报告助手", page_icon="📋", layout="wide")

from modules.auth import check_password
from modules.project import (
    init_db, list_active_projects, list_completed_projects,
    get_project, create_project, complete_project,
    save_message, get_conversation, get_export_info,
    set_export_path,
)
from modules.ui import render_sidebar, render_chat
from modules.export_manager import export_to_word

init_db()

if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None

st.markdown("""
<style>
html, body, [class*="st-"], .stMarkdown, .stText, p, li {
    font-size: 12px !important;
}
.stButton button {
    font-size: 12px !important;
    padding: 2px 6px !important;
    min-height: 26px !important;
}
code, pre { font-size: 11px !important; }
h1 { font-size: 17px !important; }
h2 { font-size: 14px !important; }
h3 { font-size: 13px !important; }
.stCaption { font-size: 11px !important; }
.stAlert { font-size: 12px !important; }

header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
.stAppToolbar { display: none !important; }
div[data-testid="stToolbar"] { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }

.main > .block-container {
    padding: 6px 12px !important;
    max-width: 100% !important;
}

section[data-testid="stSidebar"] { font-size: 12px !important; }
section[data-testid="stSidebar"] .stTextInput input { font-size: 12px !important; }
section[data-testid="stSidebar"] .stTextArea textarea { font-size: 12px !important; }
section[data-testid="stSidebar"] .stTabs button { font-size: 11px !important; }
section[data-testid="stSidebar"] h3 { font-size: 13px !important; margin-top: 6px !important; margin-bottom: 4px !important; }

section[data-testid="stSidebar"] .stExpander { margin-bottom: 2px !important; }
section[data-testid="stSidebar"] .stExpander > div > div > div { font-size: 11px !important; padding: 4px 6px !important; }

/* ── 侧边栏操作行（新建/导出/完成 + 模型/模式/联网）统一样式 ── */
section[data-testid="stSidebar"] div.row-widget.stColumns {
    gap: 4px !important;
    margin-bottom: 4px !important;
}

section[data-testid="stSidebar"] .stButton button {
    height: 32px !important;
    font-size: 11px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-radius: 6px !important;
    padding: 0 8px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

section[data-testid="stSidebar"] .stSelectbox label {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
section[data-testid="stSidebar"] .stSelectbox > div {
    min-height: 32px !important;
}
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {
    height: 32px !important;
    min-height: 32px !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] span {
    line-height: 30px !important;
    font-size: 12px !important;
}

section[data-testid="stSidebar"] hr {
    margin-top: 2px !important;
    margin-bottom: 6px !important;
    border-color: #e5e7eb !important;
    opacity: 0.6 !important;
}

div[data-testid="stChatInput"] {
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 0 !important;
}
div[data-testid="stChatInput"] .st-emotion-cache-s1k4sy {
    width: 100% !important;
}
div[data-testid="stChatInput"] textarea { 
    font-size: 12px !important; 
    width: 100% !important;
    margin: 0 !important;
    padding: 4px 8px !important;
}
.stChatMessage { padding: 4px 8px !important; }
.stChatMessage p { font-size: 12px !important; margin-bottom: 2px !important; }

section[data-testid="stSidebar"] button[kind="primary"] {
    background-color: #22c55e !important;
    border-color: #22c55e !important;
    color: white !important;
}
section[data-testid="stSidebar"] button[kind="primary"]:hover {
    background-color: #16a34a !important;
    border-color: #16a34a !important;
}

.stSelectbox div[data-baseweb="select"] span { font-size: 12px !important; }
.stSelectbox small { font-size: 10px !important; }
.stSelectbox label { font-size: 11px !important; }
.stTabs button { font-size: 12px !important; }
.stException { font-size: 11px !important; }
.stTextInput input { font-size: 12px !important; }
.stTextArea textarea { font-size: 12px !important; }
.stForm label { font-size: 12px !important; }
.project-input-wrapper { max-width: 250px; margin: 0 auto; }
</style>
""", unsafe_allow_html=True)

if not check_password():
    st.stop()

active_projects = list_active_projects()
completed_projects = list_completed_projects()

# ── 无进行中项目：显示创建页 ──
if not active_projects:
    st.markdown("<h3 style='text-align:center;'>📋 尽责报告助手</h3>", unsafe_allow_html=True)
    st.info("暂无进行中的项目，请在下方创建新项目开始工作。")
    cl, cm, cr = st.columns([1, 2, 1])
    with cm:
        with st.form("first_project_form"):
            st.markdown('<div class="project-input-wrapper">', unsafe_allow_html=True)
            company = st.text_input("公司名称", placeholder="请输入公司名称")
            st.markdown('</div>', unsafe_allow_html=True)
            if st.form_submit_button("创建项目", use_container_width=True, type="primary"):
                if company.strip():
                    pid = create_project(company.strip())
                    st.session_state.current_project_id = pid
                    st.rerun()
    if completed_projects:
        st.markdown("---")
        st.markdown("### 📁 已完成项目")
        for cp in completed_projects:
            export_info = get_export_info(cp["id"])
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{cp['name']}**")
                if cp.get("completed_at"):
                    c1.caption(f"完成：{cp['completed_at'][:10]}")
                c2.caption(f"📄 {export_info.get('export_filename', '—')}")
                path = export_info.get("export_path", "")
                if path:
                    try:
                        with open(path, "rb") as f:
                            c3.download_button("📥 下载", data=f, file_name=export_info["export_filename"],
                                               key=f"dl_c_{cp['id']}", use_container_width=True)
                    except FileNotFoundError:
                        c3.caption("已移除")
    st.stop()

# ── 有进行中项目 ──
if st.session_state.current_project_id is None:
    st.session_state.current_project_id = active_projects[0]["id"]

current_project = get_project(st.session_state.current_project_id)
if current_project is None:
    st.session_state.current_project_id = active_projects[0]["id"]
    current_project = get_project(st.session_state.current_project_id)
    if current_project is None:
        st.error("项目数据异常")
        st.stop()

current_project_id = st.session_state.current_project_id

# ── Popovers ──
if st.session_state.get("show_new_project"):
    with st.popover("新建项目", use_container_width=True):
        with st.form("new_project_form"):
            st.markdown('<div class="project-input-wrapper">', unsafe_allow_html=True)
            nc = st.text_input("公司名称", placeholder="请输入公司名称", key="new_company_input")
            st.markdown('</div>', unsafe_allow_html=True)
            if st.form_submit_button("确认创建", use_container_width=True, type="primary"):
                if nc.strip():
                    pid = create_project(nc.strip())
                    st.session_state.current_project_id = pid
                    st.session_state.show_new_project = False
                    st.rerun()

if st.session_state.get("show_export"):
    with st.popover("导出Word文档", use_container_width=True):
        export_path = export_to_word(current_project_id)
        if export_path:
            from pathlib import Path as P
            export_filename = P(export_path).name
            set_export_path(current_project_id, export_path, export_filename)
            st.success(f"✅ 文档已生成：{export_filename}")
            with open(export_path, "rb") as f:
                st.download_button("📥 点击下载", data=f, file_name=export_filename,
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   use_container_width=True, type="primary")
        else:
            st.warning("⚠️ 暂无已确认的章节内容")
        if st.button("关闭", use_container_width=True):
            st.session_state.show_export = False
            st.rerun()

if st.session_state.get("show_complete_confirm"):
    with st.popover("确认完成项目", use_container_width=True):
        export_info = get_export_info(current_project_id)
        if not export_info["has_export"]:
            st.warning("⚠️ 尚未导出Word文档。")
        st.warning(f"确定要完成项目「{current_project['name']}」吗？")
        st.caption("完成后将清理数据，仅保留Word文档。")
        c1, c2 = st.columns(2)
        if c1.button("✅ 确认完成", use_container_width=True, type="primary"):
            summary = complete_project(current_project_id)
            st.session_state.show_complete_confirm = False
            ok = sum(1 for r in summary.get("zhipu_results", []) if r["success"])
            fail = len(summary.get("zhipu_results", [])) - ok
            st.success(
                f"✅ 项目「{current_project['name']}」已完成。\n\n"
                f"清理：📁 {summary['files_deleted']}文件 💬 {summary['messages_cleared']}条对话 🏷️ 知识库{ok}成功{fail}失败"
            )
            remaining = list_active_projects()
            st.session_state.current_project_id = remaining[0]["id"] if remaining else None
            st.rerun()
        if c2.button("❌ 取消", use_container_width=True):
            st.session_state.show_complete_confirm = False
            st.rerun()

# ── 侧边栏 ──
render_sidebar(current_project_id, current_project, active_projects)

# ── 主区域：对话消息 + 报告章节 ──
render_chat(current_project_id)


