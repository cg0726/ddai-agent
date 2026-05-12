import json
import html
import streamlit as st
from pathlib import Path
from modules.config import UPLOAD_CATEGORIES, UPLOAD_DIR, UPLOAD_MAX_SIZE
from modules.project import (
    add_file, get_files, update_file_kb_status,
    add_memory, update_memory, delete_memory, get_memories,
    MEMORY_TYPES, MEMORY_TYPE_LABELS,
    get_messages, add_message, get_project_config, get_conversation,
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
        lines.append(
            f"> **[{i}] {item['title']}**  \n"
            f"> 来源：{item['source']} | 时效：{item.get('recency', '?')} | 权重：{item['weight_label']}  \n"
            f"> {item.get('extracted', item.get('snippet', ''))}\n"
        )
    lines.append(f"\n*共 {search_result['total_count']} 条*\n")
    return "\n".join(lines)


def render_sidebar(project_id: int, current_project: dict, active_projects: list):
    with st.sidebar:
        # ── 项目管理层 ──
        st.markdown(f"#### 📋 {current_project['name']}")

        project_names = {p["id"]: p["name"] for p in active_projects}
        sel_id = st.selectbox(
            "切换项目",
            options=list(project_names.keys()),
            format_func=lambda x: project_names[x],
            index=list(project_names.keys()).index(project_id) if project_id in project_names else 0,
            key="sidebar_project_selector",
            label_visibility="collapsed",
        )
        if sel_id != project_id:
            st.session_state.current_project_id = sel_id
            del_convo_cache = [k for k in st.session_state.keys() if k.startswith("convo_loaded_")]
            for k in del_convo_cache:
                del st.session_state[k]
            st.rerun()

        cb1, cb2, cb3 = st.columns(3)
        if cb1.button("➕ 新建", use_container_width=True):
            st.session_state.show_new_project = True
            st.rerun()
        if cb2.button("📄 导出", use_container_width=True):
            st.session_state.show_export = True
            st.rerun()
        if cb3.button("✔️ 完成", use_container_width=True, type="primary"):
            st.session_state.show_complete_confirm = True
            st.rerun()

        st.markdown("---")

        # ── AI 控制层 ──
        config = get_project_config(project_id)
        cm1, cm2, cm3 = st.columns([1, 1, 1])
        with cm1:
            model = st.selectbox("模型", ["Flash", "Pro"],
                                 index=0 if config["model"] == "Flash" else 1,
                                 key=f"sidebar_model_{project_id}", label_visibility="collapsed")
        with cm2:
            new_mode = st.selectbox("模式", ["问答", "报告"],
                                    index=0 if config["mode"] == "问答" else 1,
                                    key=f"sidebar_mode_{project_id}", label_visibility="collapsed")
        with cm3:
            ws_val = config["web_search"]
            label = "🌐 联网ON" if ws_val else "🌐 联网OFF"
            if st.button(label, key=f"sb_web_{project_id}", use_container_width=True,
                         type="primary" if ws_val else "secondary"):
                update_project_config(project_id, web_search=int(not ws_val))
                st.rerun()

        if new_mode != config["mode"]:
            update_project_config(project_id, mode=new_mode)
            if new_mode == "报告":
                sections = get_sections(project_id)
                if not sections:
                    with st.spinner("正在提取章节..."):
                        extract_sections(project_id)
                ts = check_template_status(project_id)
                if ts["message"]:
                    (st.info if ts["has_previous"] else st.warning)(f"ℹ️ {ts['message']}")
            st.rerun()
        if model != config["model"]:
            update_project_config(project_id, model=model)

        st.markdown("---")

        # ── 文件上传 ──
        st.markdown("#### 📂 文件上传")
        for label, cat_key in UPLOAD_CATEGORIES.items():
            with st.expander(label, expanded=False):
                uploaded_file = st.file_uploader(
                    f"上传{label}", type=None,
                    key=f"uploader_{project_id}_{cat_key}",
                    label_visibility="collapsed",
                )
                if uploaded_file is not None:
                    usk = f"upload_state_{project_id}_{cat_key}"
                    if usk not in st.session_state:
                        st.session_state[usk] = None
                    if st.session_state[usk] is None:
                        if uploaded_file.size > UPLOAD_MAX_SIZE:
                            st.error("文件超过10MB限制")
                        else:
                            sp = st.empty()
                            sp.info("⏳ 正在上传并解析...")
                            pd = UPLOAD_DIR / str(project_id) / cat_key
                            pd.mkdir(parents=True, exist_ok=True)
                            fp = pd / uploaded_file.name
                            with open(fp, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            cl = CATEGORY_LABEL_MAP.get(cat_key, "other")
                            kr = upload_to_knowledge(str(fp), cl, project_id)
                            if kr["success"]:
                                ks = kr.get("kb_status", {})
                                add_file(project_id, cat_key, uploaded_file.name, str(fp),
                                         kb_doc_id=ks.get("doc_id", ""), kb_status=ks)
                                if ks.get("status") == "completed":
                                    sp.success(f"✅ {uploaded_file.name}")
                                elif ks.get("status") == "failed":
                                    sp.warning(f"⚠️ {uploaded_file.name} 向量化失败: {ks.get('fail_reason', '?')}")
                                else:
                                    sp.success(f"✅ {uploaded_file.name} — {ks.get('status_text', '处理中')}")
                                st.session_state[usk] = "success"
                            else:
                                sp.error(f"❌ {kr['error']}")
                                st.session_state[usk] = "error"
                            st.rerun()
                existing = [f for f in get_files(project_id) if f["category"] == cat_key]
                for f in existing:
                    ksr = f.get("kb_status", "")
                    kdi = f.get("kb_doc_id", "")
                    try:
                        ks = json.loads(ksr) if isinstance(ksr, str) and ksr else {}
                    except (json.JSONDecodeError, TypeError):
                        ks = {}
                    if kdi and ks.get("status") not in ("completed", "failed"):
                        fresh = get_embedding_status(kdi)
                        if fresh["success"]:
                            ks = fresh
                            update_file_kb_status(f["id"], kb_doc_id=kdi, kb_status=fresh)
                    ss = ""
                    if ks.get("status") == "completed":
                        ss = "✅"
                    elif ks.get("status") == "failed":
                        ss = "❌"
                    elif kdi:
                        ss = "⏳"
                    st.caption(f"{ss} {f['filename']}")
                    if ks.get("status") == "failed" and kdi:
                        if st.button("🔄 重新向量化", key=f"reembed_{f['id']}"):
                            with st.spinner("..."):
                                reembed_document(kdi)
                                update_file_kb_status(f["id"], kb_doc_id=kdi, kb_status=get_embedding_status(kdi))
                            st.rerun()
                    elif ks.get("status") not in ("completed", "failed") and kdi:
                        if st.button("🔄 刷新", key=f"refresh_emb_{f['id']}"):
                            st.rerun()

        st.markdown("---")
        _memory_panel(project_id)


def _memory_panel(project_id: int):
    st.markdown("#### 🧠 记忆管理")
    t1, t2 = st.tabs(["列表", "新增"])
    with t2:
        with st.form(key=f"mf_{project_id}", clear_on_submit=True):
            mt = st.selectbox("类型", options=MEMORY_TYPES,
                              format_func=lambda x: MEMORY_TYPE_LABELS.get(x, x), key=f"mt_{project_id}")
            kw = st.text_input("关键词", placeholder="逗号分隔", key=f"mkw_{project_id}")
            ct = st.text_area("内容", height=60, placeholder="输入记忆内容...", key=f"mc_{project_id}")
            if st.form_submit_button("保存", use_container_width=True):
                if ct.strip():
                    add_memory(mt, kw.strip(), ct.strip())
                    st.success("已保存")
                    st.rerun()
    with t1:
        cs1, cs2 = st.columns([1, 1])
        with cs1:
            ft = st.selectbox("类型", options=["全部"] + MEMORY_TYPES,
                              format_func=lambda x: MEMORY_TYPE_LABELS.get(x, "全部") if x != "全部" else "全部",
                              key=f"mfilt_{project_id}", label_visibility="collapsed")
        with cs2:
            sq = st.text_input("🔍", placeholder="搜索...", key=f"ms_{project_id}", label_visibility="collapsed")
        mf = ft if ft != "全部" else None
        ss = sq if sq else None
        mems = get_memories(mtype=mf, search=ss)
        if not mems:
            st.caption("暂无")
        for mem in mems:
            with st.container(border=True):
                tl = MEMORY_TYPE_LABELS.get(mem["type"], mem["type"])
                ek = f"em_{mem['id']}"
                if st.session_state.get(ek):
                    nt = st.selectbox("类型", options=MEMORY_TYPES,
                                      format_func=lambda x: MEMORY_TYPE_LABELS.get(x, x),
                                      index=MEMORY_TYPES.index(mem["type"]) if mem["type"] in MEMORY_TYPES else 0,
                                      key=f"met_{mem['id']}")
                    nk = st.text_input("关键词", value=mem["keywords"], key=f"mek_{mem['id']}")
                    nv = st.text_area("内容", value=mem["content"], height=60, key=f"mev_{mem['id']}", label_visibility="collapsed")
                    c1, c2 = st.columns(2)
                    if c1.button("保存", key=f"msv_{mem['id']}", use_container_width=True):
                        update_memory(mem["id"], nt, nk, nv)
                        st.session_state[ek] = False
                        st.rerun()
                    if c2.button("取消", key=f"mcl_{mem['id']}", use_container_width=True):
                        st.session_state[ek] = False
                        st.rerun()
                else:
                    st.caption(f"[{tl}] {mem['keywords']} — {mem['content'][:60]}{'...' if len(mem['content']) > 60 else ''}")
                    c1, c2 = st.columns(2)
                    if c1.button("编辑", key=f"med_{mem['id']}", use_container_width=True):
                        st.session_state[ek] = True
                        st.rerun()
                    if c2.button("删除", key=f"mdl_{mem['id']}", use_container_width=True):
                        delete_memory(mem["id"])
                        st.rerun()


def _build_streaming_display(reasoning: str, content: str, final: bool = False) -> str:
    cursor = "" if final else "▌"
    if reasoning:
        escaped_reasoning = html.escape(reasoning)
        return (
            '<details open><summary>🧠 思考过程</summary>\n\n'
            '<div style="max-height:400px;overflow-y:auto;background:#f8f9fa;'
            'border-radius:6px;padding:8px 12px;font-size:11px;'
            'white-space:pre-wrap;word-break:break-word;color:#555;">\n'
            f'{escaped_reasoning}\n'
            '</div>\n'
            '</details>\n\n'
            f'{content}{cursor}'
        )
    return f'{content}{cursor}'


def render_chat(project_id: int):
    config = get_project_config(project_id)
    current_mode = config["mode"]

    # ── 报告模式 ──
    if current_mode == "报告":
        sections = get_sections(project_id)
        if not sections:
            sections = extract_sections(project_id)
        progress = get_section_progress(project_id)
        if progress["total"] > 0:
            st.progress(progress["confirmed"] / progress["total"], text=f"📊 {progress['confirmed']}/{progress['total']} 章")

        current = get_current_section(project_id)
        if current is None and progress["confirmed"] > 0:
            st.success("🎉 所有章节已完成！请导出文档。")
        elif current is not None:
            idx = current["_index"]
            rk = f"sec_result_{project_id}_{idx}"
            with st.expander(f"📄 {current['title']}", expanded=True):
                st.caption(current.get("description", ""))
                if rk not in st.session_state:
                    st.session_state[rk] = None
                if st.session_state[rk] is None:
                    if st.button(f"🚀 生成「{current['title']}」", key=f"gen_{project_id}_{idx}",
                                 use_container_width=True, type="primary"):
                        with st.chat_message("assistant"):
                            ph = st.empty()
                            ph.info("⏳ 正在生成...")
                            full_reasoning = ""
                            full_content = ""
                            for chunk in chat(project_id,
                                              f"请撰写「{current['title']}」章节。{current.get('description', '')}",
                                              config["model"], current_mode, config["web_search"]):
                                if chunk["type"] == "reasoning":
                                    full_reasoning += chunk["text"]
                                elif chunk["type"] == "content":
                                    full_content += chunk["text"]
                                elif chunk["type"] == "error":
                                    full_content += chunk["text"]
                                ph.markdown(
                                    _build_streaming_display(full_reasoning, full_content),
                                    unsafe_allow_html=True,
                                )
                            ph.markdown(
                                _build_streaming_display(full_reasoning, full_content, final=True),
                                unsafe_allow_html=True,
                            )
                            st.session_state[rk] = full_content
                        st.rerun()
                else:
                    st.markdown(st.session_state[rk])
                    ca, cb, cc = st.columns(3)
                    if ca.button("✅ 接受", key=f"acc_{project_id}_{idx}", use_container_width=True, type="primary"):
                        content = st.session_state[rk]
                        confirm_section(project_id, idx, content)
                        st.session_state[rk] = None
                        add_message(project_id, "assistant", f"**📄 {current['title']}**\n\n{content}",
                                    sources=[{"source": "AI生成", "section": current["title"]}])
                        st.rerun()
                    ek = f"edit_mode_{project_id}_{idx}"
                    if not st.session_state.get(ek):
                        if cb.button("✏️ 编辑", key=f"ed_{project_id}_{idx}", use_container_width=True):
                            st.session_state[ek] = True
                            st.rerun()
                    rwk = f"rw_{project_id}_{idx}"
                    if not st.session_state.get(rwk):
                        if cc.button("🔄 重写", key=f"rwb_{project_id}_{idx}", use_container_width=True):
                            st.session_state[rwk] = True
                            st.rerun()
                    if st.session_state.get(ek):
                        edited = st.text_area("编辑", value=st.session_state[rk], height=150, key=f"editor_{project_id}_{idx}")
                        ec1, ec2 = st.columns(2)
                        if ec1.button("💾 保存", key=f"sv_{project_id}_{idx}", use_container_width=True, type="primary"):
                            confirm_section(project_id, idx, edited)
                            st.session_state[rk] = None
                            st.session_state[ek] = False
                            add_message(project_id, "assistant", f"**📄 {current['title']}**\n\n{edited}",
                                        sources=[{"source": "AI+编辑", "section": current["title"]}])
                            st.rerun()
                        if ec2.button("取消", key=f"cce_{project_id}_{idx}", use_container_width=True):
                            st.session_state[ek] = False
                            st.rerun()
                    if st.session_state.get(rwk):
                        fb = st.text_area("重写意见", placeholder="说明修改方向...", height=60, key=f"fb_{project_id}_{idx}")
                        rc1, rc2 = st.columns(2)
                        if rc1.button("🔄 重新生成", key=f"drw_{project_id}_{idx}", use_container_width=True, type="primary"):
                            st.session_state[rk] = None
                            st.session_state[rwk] = False
                            st.rerun()
                        if rc2.button("取消", key=f"ccr_{project_id}_{idx}", use_container_width=True):
                            st.session_state[rwk] = False
                            st.rerun()

    # ── 对话历史 ──
    convo_cache = f"convo_loaded_{project_id}"
    if convo_cache not in st.session_state:
        get_conversation(project_id)
        st.session_state[convo_cache] = True

    messages = get_messages(project_id)
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(msg["content"], unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # ── 输入框 ──
    cfg = get_project_config(project_id)
    prompt = st.chat_input("请输入问题..." if cfg["mode"] != "报告" else "章节补充要求...", key=f"ci_{project_id}")
    if prompt:
        cfg = get_project_config(project_id)
        add_message(project_id, "user", prompt)
        st.chat_message("user").markdown(prompt)
        with st.chat_message("assistant"):
            ph = st.empty()
            ph.info("⏳ 正在生成...")
            sl = []
            full_reasoning = ""
            full_content = ""
            for chunk in chat(project_id, prompt, cfg["model"], cfg["mode"], cfg["web_search"]):
                if chunk["type"] == "reasoning":
                    full_reasoning += chunk["text"]
                elif chunk["type"] == "content":
                    full_content += chunk["text"]
                elif chunk["type"] == "error":
                    full_content += chunk["text"]
                ph.markdown(
                    _build_streaming_display(full_reasoning, full_content),
                    unsafe_allow_html=True,
                )
            ph.markdown(
                _build_streaming_display(full_reasoning, full_content, final=True),
                unsafe_allow_html=True,
            )
            full_display = _build_streaming_display(full_reasoning, full_content, final=True)
            if cfg["web_search"]:
                sr = search_and_format(prompt, use_extract=False)
                if sr["success"]:
                    for it in sr.get("results", []):
                        sl.append({"title": it["title"], "source": it["source"], "weight": it["weight"], "url": it["url"]})
            add_message(project_id, "assistant", full_display, sources=sl if sl else None)
        st.rerun()
