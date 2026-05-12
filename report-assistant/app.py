import streamlit as st

st.set_page_config(page_title="尽责报告助手", page_icon="📋", layout="wide")

from modules.auth import check_password
from modules.project import (
    init_db, list_active_projects, list_completed_projects,
    get_project, create_project, complete_project,
    save_message, get_conversation, get_export_info,
    set_export_path,
)
from modules.ui import render_sidebar, render_chat, render_chat_bottom
from modules.export_manager import export_to_word

init_db()

if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None

st.markdown("""
<style>
/* ── Global font size reduction ── */
html, body, [class*="st-"], .stMarkdown, .stText, p, li, span, div {
    font-size: 14px !important;
}
.stSelectbox label, .stCheckbox label {
    font-size: 13px !important;
}
.stButton button {
    font-size: 13px !important;
}
code, pre {
    font-size: 12px !important;
}
h1 { font-size: 20px !important; }
h2 { font-size: 17px !important; }
h3 { font-size: 15px !important; }

/* ── Hide Streamlit header toolbar (Deploy, menu, etc.) ── */
header[data-testid="stHeader"] {
    display: none !important;
}
#MainMenu {
    display: none !important;
}
.stAppToolbar {
    display: none !important;
}
div[data-testid="stToolbar"] {
    display: none !important;
}
div[data-testid="stDecoration"] {
    display: none !important;
}

/* ── Full height flex layout ── */
.main > .block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
    height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
}

/* ── Fixed top bar ── */
#top-bar {
    flex-shrink: 0;
    background: white;
    padding: 6px 16px 2px 16px;
    border-bottom: 1px solid #e0e0e0;
    z-index: 999;
}

/* ── Scrollable chat area ── */
#chat-area {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 6px 16px;
}

/* ── Fixed bottom bar ── */
#bottom-bar {
    flex-shrink: 0;
    background: white;
    padding: 4px 16px 8px 16px;
    border-top: 1px solid #e0e0e0;
    z-index: 999;
}

/* ── Unified bottom controls styling ── */
#bottom-bar div[data-testid="stSelectbox"] {
    min-height: 32px !important;
}
#bottom-bar div[data-testid="stSelectbox"] > div {
    min-height: 32px !important;
    font-size: 13px !important;
}
#bottom-bar div[data-testid="stSelectbox"] label {
    font-size: 12px !important;
    margin-bottom: 0 !important;
}
#bottom-bar div[data-testid="stCheckbox"] {
    min-height: 32px !important;
    display: flex !important;
    align-items: center !important;
}
#bottom-bar div[data-testid="stCheckbox"] label {
    font-size: 13px !important;
    gap: 4px !important;
}

/* ── Web search checkbox: green active, gray inactive ── */
.web-search-active label span[data-testid="check"] svg {
    fill: #22c55e !important;
}
.web-search-inactive label span[data-testid="check"] svg {
    fill: #9ca3af !important;
}

/* ── Chat input styling ── */
div[data-testid="stChatInput"] {
    border: 1px solid #d0d0d0;
    border-radius: 8px;
    margin-top: 2px;
}

/* ── Sidebar font adjustment ── */
section[data-testid="stSidebar"] {
    font-size: 13px !important;
}

/* ── Tabs and form labels ── */
.stTabs button {
    font-size: 13px !important;
}
.stForm label {
    font-size: 13px !important;
}
.stCaption {
    font-size: 12px !important;
}
.stAlert {
    font-size: 13px !important;
}
.stException {
    font-size: 12px !important;
}
.stSelectbox small {
    font-size: 11px !important;
}
.stSelectbox div[data-baseweb="select"] span {
    font-size: 13px !important;
}
</style>
""", unsafe_allow_html=True)

if not check_password():
    st.stop()

active_projects = list_active_projects()
completed_projects = list_completed_projects()

if not active_projects:
    st.markdown("<h1 style='text-align: center;'>📋 尽责报告助手</h1>", unsafe_allow_html=True)
    st.markdown("---")
    st.info("暂无进行中的项目，请在下方创建新项目开始工作。")

    col_left, col_mid, col_right = st.columns([1, 2, 1])
    with col_mid:
        with st.form("first_project_form"):
            company = st.text_input("公司名称", placeholder="请输入公司名称")
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
            name = cp["name"]
            completed_at = cp.get("completed_at", "")[:10] if cp.get("completed_at") else ""
            export_name = export_info.get("export_filename", "")
            export_path_str = export_info.get("export_path", "")
            with st.container(border=True):
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    st.markdown(f"**{name}**")
                    if completed_at:
                        st.caption(f"完成时间：{completed_at}")
                with cols[1]:
                    if export_name:
                        st.caption(f"📄 {export_name}")
                with cols[2]:
                    if export_path_str:
                        try:
                            with open(export_path_str, "rb") as f:
                                st.download_button("📥 下载", data=f,
                                                   file_name=export_name,
                                                   key=f"dl_c_{cp['id']}",
                                                   use_container_width=True)
                        except FileNotFoundError:
                            st.caption("文件已移除")
    st.stop()

if st.session_state.current_project_id is None:
    st.session_state.current_project_id = active_projects[0]["id"]

current_project = get_project(st.session_state.current_project_id)
if current_project is None:
    st.session_state.current_project_id = active_projects[0]["id"]
    current_project = get_project(st.session_state.current_project_id)
    if current_project is None:
        st.error("项目数据异常，请重新登录")
        st.stop()

# ── Top bar ──
st.markdown('<div id="top-bar">', unsafe_allow_html=True)
col_t1, col_t2, col_t3, col_t4, col_t5 = st.columns([2, 2, 1, 1, 1])
with col_t1:
    st.markdown(f"**📋 {current_project['name']}**")
with col_t2:
    project_names = {p["id"]: p["name"] for p in active_projects}
    selected_id = st.selectbox(
        "切换项目",
        options=list(project_names.keys()),
        format_func=lambda x: project_names[x],
        index=list(project_names.keys()).index(st.session_state.current_project_id)
        if st.session_state.current_project_id in project_names
        else 0,
        key="project_selector",
        label_visibility="collapsed",
        placeholder="选择项目...",
    )
    if selected_id != st.session_state.current_project_id:
        st.session_state.current_project_id = selected_id
        del_convo_cache = [k for k in st.session_state.keys() if k.startswith("convo_loaded_")]
        for k in del_convo_cache:
            del st.session_state[k]
        st.rerun()
with col_t3:
    if st.button("➕ 新建", use_container_width=True):
        st.session_state.show_new_project = True
        st.rerun()
with col_t4:
    if st.button("📄 导出", use_container_width=True):
        st.session_state.show_export = True
        st.rerun()
with col_t5:
    if st.button("✔️ 完成", use_container_width=True, type="primary"):
        st.session_state.show_complete_confirm = True
        st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ── Popovers ──
if st.session_state.get("show_new_project"):
    with st.popover("新建项目", use_container_width=True):
        with st.form("new_project_form"):
            new_company = st.text_input("公司名称", placeholder="请输入公司名称", key="new_company_input")
            if st.form_submit_button("确认创建", use_container_width=True, type="primary"):
                if new_company.strip():
                    pid = create_project(new_company.strip())
                    st.session_state.current_project_id = pid
                    st.session_state.show_new_project = False
                    st.rerun()

if st.session_state.get("show_export"):
    with st.popover("导出Word文档", use_container_width=True):
        st.info("正在生成Word文档...")
        export_path = export_to_word(st.session_state.current_project_id)
        if export_path:
            from pathlib import Path as P
            export_filename = P(export_path).name
            set_export_path(st.session_state.current_project_id, export_path, export_filename)
            st.success(f"✅ 文档已生成：{export_filename}")
            with open(export_path, "rb") as f:
                st.download_button(
                    "📥 点击下载",
                    data=f,
                    file_name=export_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    type="primary",
                )
        else:
            st.warning("⚠️ 暂无已确认的章节内容，请在报告模式下完成至少一章后再导出。")
        if st.button("关闭", use_container_width=True):
            st.session_state.show_export = False
            st.rerun()

if st.session_state.get("show_complete_confirm"):
    with st.popover("确认完成项目", use_container_width=True):
        export_info = get_export_info(st.session_state.current_project_id)
        if not export_info["has_export"]:
            st.warning("⚠️ 尚未导出Word文档。")
            st.caption("建议先点击「📄 导出Word」生成并下载报告，再完成项目。")
            st.markdown("---")
        st.warning(f"确定要完成项目「{current_project['name']}」吗？")
        st.caption("完成后将清理所有中间数据：① 删除智谱知识库文件 ② 删除本地上传文件 ③ 清除对话记录。仅保留导出的Word文档。")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 确认完成", use_container_width=True, type="primary"):
                summary = complete_project(st.session_state.current_project_id)
                st.session_state.show_complete_confirm = False
                zhipu_ok = sum(1 for r in summary.get("zhipu_results", []) if r["success"])
                zhipu_fail = len(summary.get("zhipu_results", [])) - zhipu_ok
                st.success(
                    f"✅ 项目「{current_project['name']}」已完成。\n\n"
                    f"清理摘要：\n"
                    f"- 📁 本地文件清理: {summary['files_deleted']} 个\n"
                    f"- 💬 对话消息清除: {summary['messages_cleared']} 条\n"
                    f"- 🏷️ 智谱知识库文件: {zhipu_ok} 成功, {zhipu_fail} 失败"
                )
                remaining = list_active_projects()
                if remaining:
                    st.session_state.current_project_id = remaining[0]["id"]
                else:
                    st.session_state.current_project_id = None
                st.rerun()
        with c2:
            if st.button("❌ 取消", use_container_width=True):
                st.session_state.show_complete_confirm = False
                st.rerun()

# ── Main chat area (scrollable) ──
st.markdown('<div id="chat-area">', unsafe_allow_html=True)
current_project_id = st.session_state.current_project_id
if current_project_id is not None:
    convo_cache_key = f"convo_loaded_{current_project_id}"
    if convo_cache_key not in st.session_state:
        conversation = get_conversation(current_project_id)
        st.session_state[convo_cache_key] = True
    files = render_sidebar(current_project_id)
    render_chat(current_project_id)
st.markdown('</div>', unsafe_allow_html=True)

# ── Bottom bar (fixed: controls + input) ──
st.markdown('<div id="bottom-bar">', unsafe_allow_html=True)
if current_project_id is not None:
    render_chat_bottom(current_project_id)
st.markdown('</div>', unsafe_allow_html=True)

# ── Completed projects (collapsible, at very bottom) ──
if completed_projects:
    st.markdown("---")
    with st.expander(f"📁 已完成项目 ({len(completed_projects)} 个)", expanded=False):
        for cp in completed_projects:
            export_info = get_export_info(cp["id"])
            name = cp["name"]
            completed_at = cp.get("completed_at", "")[:10] if cp.get("completed_at") else ""
            export_name = export_info.get("export_filename", "")
            export_path_str = export_info.get("export_path", "")
            with st.container(border=True):
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    st.markdown(f"**{name}**")
                    if completed_at:
                        st.caption(f"完成时间：{completed_at}")
                with cols[1]:
                    if export_name:
                        st.caption(f"📄 {export_name}")
                    else:
                        st.caption("无导出文件")
                with cols[2]:
                    if export_path_str:
                        try:
                            with open(export_path_str, "rb") as f:
                                st.download_button("📥 下载", data=f,
                                                   file_name=export_name,
                                                   key=f"dl_{cp['id']}",
                                                   use_container_width=True)
                        except FileNotFoundError:
                            st.caption("文件已移除")
