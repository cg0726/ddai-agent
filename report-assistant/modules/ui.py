import json
import streamlit as st
from pathlib import Path
from modules.config import UPLOAD_CATEGORIES, UPLOAD_DIR, UPLOAD_MAX_SIZE
from modules.project import (
    add_file, get_files, update_file_kb_status,
    add_memory, update_memory, delete_memory, get_memories,
    MEMORY_TYPES, MEMORY_TYPE_LABELS,
    get_messages, add_message, get_project_config,
    update_project_config, get_sections, confirm_section,
    get_current_section, get_section_progress, update_section,
)
from modules.knowledge_manager import (
    CATEGORY_LABEL_MAP,
    upload_to_knowledge,
    check_template_status,
    get_embedding_status,
    reembed_document,
)
from modules.search_manager import search_and_format
from modules.chat_engine import chat, extract_sections


def format_search_results(search_result: dict) -> str:
    if not search_result["success"] or search_result["total_count"] == 0:
        return ""
    lines = ["**🔍 联网搜索结果**\n"]
    for i, item in enumerate(search_result["results"], 1):
        weight_info = item["weight_label"]
        recency = item.get("recency", "未知")
        content = item.get("extracted", item.get("snippet", "无摘要"))
        lines.append(
            f"> **[{i}] {item['title']}**  \n"
            f"> 来源：{item['source']} | 时效：{recency} | 权重：{weight_info}  \n"
            f"> {content}\n"
        )
    lines.append(f"\n*共 {search_result['total_count']} 条结果*\n")
    return "\n".join(lines)


def render_sidebar(project_id: int):
    with st.sidebar:
        st.markdown("### 📂 文件上传")
        for label, cat_key in UPLOAD_CATEGORIES.items():
            with st.expander(label, expanded=False):
                uploaded_file = st.file_uploader(
                    f"上传{label}", type=None,
                    key=f"uploader_{project_id}_{cat_key}",
                    label_visibility="collapsed",
                )
                if uploaded_file is not None:
                    upload_state_key = f"upload_state_{project_id}_{cat_key}"
                    if upload_state_key not in st.session_state:
                        st.session_state[upload_state_key] = None
                    if st.session_state[upload_state_key] is None:
                        if uploaded_file.size > UPLOAD_MAX_SIZE:
                            st.error("文件大小超过10MB限制，请重新选择")
                        else:
                            status_placeholder = st.empty()
                            status_placeholder.info("⏳ 正在上传并解析...")
                            project_dir = UPLOAD_DIR / str(project_id) / cat_key
                            project_dir.mkdir(parents=True, exist_ok=True)
                            file_path = project_dir / uploaded_file.name
                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                            category_label = CATEGORY_LABEL_MAP.get(cat_key, "other")
                            kb_result = upload_to_knowledge(str(file_path), category_label, project_id)

                            if kb_result["success"]:
                                kb_status = kb_result.get("kb_status", {})
                                add_file(project_id, cat_key, uploaded_file.name, str(file_path),
                                         kb_doc_id=kb_status.get("doc_id", ""),
                                         kb_status=kb_status)
                                if kb_status.get("status") == "completed":
                                    status_placeholder.success(f"✅ {uploaded_file.name} 已入库 — 向量化完成")
                                elif kb_status.get("status") == "failed":
                                    status_placeholder.warning(f"⚠️ {uploaded_file.name} 上传成功，但向量化失败: {kb_status.get('fail_reason', '未知')}")
                                else:
                                    status_placeholder.success(f"✅ {uploaded_file.name} 已入库 — {kb_status.get('status_text', '向量化处理中')}")
                                st.session_state[upload_state_key] = "success"
                            else:
                                status_placeholder.error(f"❌ {uploaded_file.name} 入库失败: {kb_result['error']}")
                                st.session_state[upload_state_key] = "error"
                            st.rerun()
                existing = [f for f in get_files(project_id) if f["category"] == cat_key]
                if existing:
                    for f in existing:
                        kb_status_raw = f.get("kb_status", "")
                        kb_doc_id = f.get("kb_doc_id", "")
                        try:
                            kb_status = json.loads(kb_status_raw) if isinstance(kb_status_raw, str) and kb_status_raw else {}
                        except (json.JSONDecodeError, TypeError):
                            kb_status = {}

                        if kb_doc_id and kb_status.get("status") not in ("completed", "failed"):
                            fresh = get_embedding_status(kb_doc_id)
                            if fresh["success"]:
                                kb_status = fresh
                                update_file_kb_status(f["id"], kb_doc_id=kb_doc_id, kb_status=fresh)

                        status_str = ""
                        if kb_status.get("status") == "completed":
                            status_str = "✅"
                        elif kb_status.get("status") == "failed":
                            status_str = "❌"
                        elif kb_doc_id:
                            status_str = "⏳"
                        st.caption(f"{status_str} {f['filename']}")

                        if kb_status.get("status") == "failed" and kb_doc_id:
                            if st.button("🔄 重新向量化", key=f"reembed_{f['id']}"):
                                with st.spinner("重新向量化..."):
                                    reembed_document(kb_doc_id)
                                    new_emb = get_embedding_status(kb_doc_id)
                                    update_file_kb_status(f["id"], kb_doc_id=kb_doc_id, kb_status=new_emb)
                                st.rerun()
                        elif kb_status.get("status") not in ("completed", "failed") and kb_doc_id:
                            if st.button("🔄 刷新状态", key=f"refresh_emb_{f['id']}"):
                                st.rerun()
        st.markdown("---")
        render_memory_panel(project_id)
    return get_files(project_id)


def render_memory_panel(project_id: int):
    st.markdown("### 🧠 记忆管理")
    tab1, tab2 = st.tabs(["记忆列表", "新增记忆"])
    with tab2:
        with st.form(key=f"new_memory_form_{project_id}", clear_on_submit=True):
            mtype = st.selectbox("类型", options=MEMORY_TYPES,
                                 format_func=lambda x: MEMORY_TYPE_LABELS.get(x, x),
                                 key=f"mem_type_{project_id}")
            keywords = st.text_input("关键词", placeholder="逗号分隔，如：风格,语气", key=f"mem_kw_{project_id}")
            content = st.text_area("内容", height=100, placeholder="输入记忆内容...", key=f"mem_ct_{project_id}")
            if st.form_submit_button("保存记忆", use_container_width=True):
                if content.strip():
                    add_memory(mtype, keywords.strip(), content.strip())
                    st.success("记忆已保存")
                    st.rerun()
    with tab1:
        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            filter_type = st.selectbox("筛选类型", options=["全部"] + MEMORY_TYPES,
                                       format_func=lambda x: MEMORY_TYPE_LABELS.get(x, "全部") if x != "全部" else "全部",
                                       key=f"mem_filter_{project_id}", label_visibility="collapsed")
        with col_s2:
            search_q = st.text_input("🔍", placeholder="搜索记忆...", key=f"search_memory_{project_id}", label_visibility="collapsed")
        mtype_filter = filter_type if filter_type != "全部" else None
        search_str = search_q if search_q else None
        memories = get_memories(mtype=mtype_filter, search=search_str)
        if not memories:
            st.caption("暂无记忆条目")
        for mem in memories:
            with st.container(border=True):
                type_label = MEMORY_TYPE_LABELS.get(mem["type"], mem["type"])
                edit_key = f"edit_mem_{mem['id']}"
                if st.session_state.get(edit_key, False):
                    new_type = st.selectbox("类型", options=MEMORY_TYPES,
                                            format_func=lambda x: MEMORY_TYPE_LABELS.get(x, x),
                                            index=MEMORY_TYPES.index(mem["type"]) if mem["type"] in MEMORY_TYPES else 0,
                                            key=f"mem_edit_type_{mem['id']}")
                    new_kw = st.text_input("关键词", value=mem["keywords"], key=f"mem_edit_kw_{mem['id']}")
                    new_val = st.text_area("内容", value=mem["content"], key=f"mem_input_{mem['id']}", height=80, label_visibility="collapsed")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("保存", key=f"mem_save_{mem['id']}", use_container_width=True):
                            update_memory(mem["id"], new_type, new_kw, new_val)
                            st.session_state[edit_key] = False
                            st.rerun()
                    with c2:
                        if st.button("取消", key=f"mem_cancel_{mem['id']}", use_container_width=True):
                            st.session_state[edit_key] = False
                            st.rerun()
                else:
                    st.caption(f"[{type_label}] {mem['keywords']} — {mem['content'][:80]}{'...' if len(mem['content']) > 80 else ''}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("编辑", key=f"mem_edit_{mem['id']}", use_container_width=True):
                            st.session_state[edit_key] = True
                            st.rerun()
                    with c2:
                        if st.button("删除", key=f"mem_del_{mem['id']}", use_container_width=True):
                            delete_memory(mem["id"])
                            st.rerun()


def render_chat(project_id: int, fixed_bottom: bool = False):
    """Render chat messages and report mode section (scrollable area)."""
    config = get_project_config(project_id)
    current_mode = config["mode"]

    # ── 报告模式：章节进度与生成（在滚动区域中） ──
    if current_mode == "报告":
        sections = get_sections(project_id)
        if not sections:
            sections = extract_sections(project_id)

        progress = get_section_progress(project_id)
        st.markdown(f"**📊 报告进度**: {progress['confirmed']}/{progress['total']} 章已完成")
        if progress["total"] > 0:
            st.progress(progress["confirmed"] / progress["total"])

        current = get_current_section(project_id)
        if current is None and progress["confirmed"] > 0:
            st.success("🎉 **所有章节已完成！** 请导出文档。")
        elif current is not None:
            idx = current["_index"]
            result_key = f"sec_result_{project_id}_{idx}"

            with st.expander(f"📄 当前章节：{current['title']}", expanded=True):
                st.caption(current.get("description", ""))
                if result_key not in st.session_state:
                    st.session_state[result_key] = None

                if st.session_state[result_key] is None:
                    if st.button(f"🚀 生成「{current['title']}」", key=f"gen_btn_{project_id}_{idx}",
                                 use_container_width=True, type="primary"):
                        with st.chat_message("assistant"):
                            placeholder = st.empty()
                            placeholder.info("⏳ 正在生成，请稍候...")
                            full = ""
                            prompt = f"请撰写尽责调查报告的「{current['title']}」章节。{current.get('description', '')}"
                            for chunk in chat(project_id, prompt, config["model"], current_mode, config["web_search"]):
                                full += chunk
                                placeholder.markdown(full + "▌")
                            placeholder.markdown(full)
                            st.session_state[result_key] = full
                        st.rerun()
                else:
                    st.markdown(st.session_state[result_key])
                    c_a, c_b, c_c = st.columns(3)
                    with c_a:
                        if st.button("✅ 接受", key=f"accept_{project_id}_{idx}", use_container_width=True, type="primary"):
                            content = st.session_state[result_key]
                            confirm_section(project_id, idx, content)
                            st.session_state[result_key] = None
                            add_message(project_id, "assistant",
                                        f"**📄 {current['title']}**\n\n{content}",
                                        sources=[{"source": "AI生成", "section": current["title"]}])
                            st.rerun()
                    with c_b:
                        edit_key = f"edit_mode_{project_id}_{idx}"
                        if not st.session_state.get(edit_key):
                            if st.button("✏️ 编辑", key=f"edit_{project_id}_{idx}", use_container_width=True):
                                st.session_state[edit_key] = True
                                st.rerun()
                    with c_c:
                        rewrite_key = f"rewrite_input_{project_id}_{idx}"
                        if not st.session_state.get(rewrite_key):
                            if st.button("🔄 重写", key=f"rewrite_{project_id}_{idx}", use_container_width=True):
                                st.session_state[rewrite_key] = True
                                st.rerun()

                    edit_key = f"edit_mode_{project_id}_{idx}"
                    if st.session_state.get(edit_key):
                        edited = st.text_area("编辑内容", value=st.session_state[result_key],
                                              height=200, key=f"editor_{project_id}_{idx}")
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            if st.button("💾 保存修改", key=f"save_edit_{project_id}_{idx}",
                                         use_container_width=True, type="primary"):
                                confirm_section(project_id, idx, edited)
                                st.session_state[result_key] = None
                                st.session_state[edit_key] = False
                                add_message(project_id, "assistant",
                                            f"**📄 {current['title']}**\n\n{edited}",
                                            sources=[{"source": "AI生成+人工编辑", "section": current["title"]}])
                                st.rerun()
                        with ec2:
                            if st.button("取消", key=f"cancel_edit_{project_id}_{idx}", use_container_width=True):
                                st.session_state[edit_key] = False
                                st.rerun()

                    rewrite_key = f"rewrite_input_{project_id}_{idx}"
                    if st.session_state.get(rewrite_key):
                        feedback = st.text_area("重写意见", placeholder="请说明需要修改的方向...",
                                                key=f"feedback_{project_id}_{idx}", height=80)
                        rc1, rc2 = st.columns(2)
                        with rc1:
                            if st.button("🔄 重新生成", key=f"do_rewrite_{project_id}_{idx}",
                                         use_container_width=True, type="primary"):
                                st.session_state[result_key] = None
                                st.session_state[rewrite_key] = False
                                st.rerun()
                        with rc2:
                            if st.button("取消", key=f"cancel_rewrite_{project_id}_{idx}",
                                         use_container_width=True):
                                st.session_state[rewrite_key] = False
                                st.rerun()

    # ── 对话历史 ──
    messages = get_messages(project_id)
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def render_chat_bottom(project_id: int):
    """Render fixed bottom bar with model/mode controls and chat input."""
    config = get_project_config(project_id)

    col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
    with col_b1:
        model = st.selectbox("模型", ["Flash", "Pro"],
                             index=0 if config["model"] == "Flash" else 1,
                             key=f"model_bottom_{project_id}", label_visibility="collapsed")
    with col_b2:
        new_mode = st.selectbox("模式", ["问答", "报告"],
                                index=0 if config["mode"] == "问答" else 1,
                                key=f"mode_bottom_{project_id}", label_visibility="collapsed")
    with col_b3:
        web_search_val = config["web_search"]
        web_class = "web-search-active" if web_search_val else "web-search-inactive"
        st.markdown(f'<div class="{web_class}">', unsafe_allow_html=True)
        web_search = st.checkbox("联网搜索", value=web_search_val,
                                 key=f"web_bottom_{project_id}")
        st.markdown('</div>', unsafe_allow_html=True)

    mode_changed = new_mode != config["mode"]
    if mode_changed:
        update_project_config(project_id, mode=new_mode)
        if new_mode == "报告":
            sections = get_sections(project_id)
            if not sections:
                with st.spinner("正在提取报告章节结构..."):
                    extract_sections(project_id)
            template_status = check_template_status(project_id)
            if template_status["message"]:
                if template_status["has_previous"]:
                    st.info(f"ℹ️ {template_status['message']}")
                else:
                    st.warning(f"⚠️ {template_status['message']}")
        st.rerun()

    if model != config["model"]:
        update_project_config(project_id, model=model)
    if web_search != config["web_search"]:
        update_project_config(project_id, web_search=int(web_search))

    current_mode = new_mode
    prompt = st.chat_input("请输入您的问题..." if current_mode != "报告" else "请输入对该章节的补充要求...",
                           key=f"chat_input_{project_id}")
    if prompt:
        cfg = get_project_config(project_id)
        add_message(project_id, "user", prompt)
        st.chat_message("user").markdown(prompt)
        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.info("⏳ 正在生成回答...")
            sources_list = []
            full_response = ""
            for chunk in chat(project_id, prompt, cfg["model"], cfg["mode"], cfg["web_search"]):
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            if cfg["web_search"]:
                search_result = search_and_format(prompt, use_extract=False)
                if search_result["success"]:
                    for item in search_result.get("results", []):
                        sources_list.append({
                            "title": item["title"],
                            "source": item["source"],
                            "weight": item["weight"],
                            "url": item["url"],
                        })
            add_message(project_id, "assistant", full_response,
                        sources=sources_list if sources_list else None)
        st.rerun()
