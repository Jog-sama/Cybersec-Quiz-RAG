# AI Citation:

# App scaffolding drafted with Claude Sonnet 5 via Claude Code Assistant on 09/07/2026 at 4:55 PM EST.

# Since claude code chats are local jsons and can't be shared, here are the screenshots.
# https://drive.google.com/drive/folders/1BhWHL2m5BKwpO7tlVkxD5e3FP8f7AH-Q?usp=share_link

import streamlit as st
from rag_engine import (
    API_KEY,
    extract_text,
    make_chunks,
    get_chroma,
    store_chunks_in_db,
    generate_quiz,
    grade_quiz,
)

st.set_page_config(page_title="CyberSec Quiz Generator", page_icon="🔒", layout="wide")

#init session state vars
for key in ["quiz_data", "quiz_results"]:
    if key not in st.session_state:
        st.session_state[key] = None
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

# ---- sidebar: document upload ----
with st.sidebar:
    st.header("📚 Document Manager")
    col = get_chroma()
    st.info(f"Chunks in database: {col.count()}")

    uploaded = st.file_uploader("Drop PDFs or text files",
                                type=["pdf", "txt"],
                                accept_multiple_files=True)

    if uploaded and st.button("Process Documents", type="primary"):
        with st.spinner("Processing..."):
            total = 0
            for f in uploaded:
                text = extract_text(f)
                if not text.strip():
                    continue
                chunks = make_chunks(text)
                stored = store_chunks_in_db(chunks, f.name)
                total += stored
                st.success(f"{f.name}: {stored} chunks")

            st.success(f"Done! {total} chunks added")
            st.rerun()

    if st.button("🗑️ Clear Database"):
        if "chroma_client" in st.session_state:
            st.session_state.chroma_client.delete_collection("cybersec_docs")
            del st.session_state["chroma_col"]
        st.session_state.quiz_data = None
        st.session_state.quiz_submitted = False
        st.rerun()

    st.divider()
    if API_KEY:
        st.success("API Key: Loaded ✓")
    else:
        st.error("API Key: Missing!")

# ---- main area: quiz ----
st.title("🔒 CyberSec Quiz Generator")
st.caption("Upload cybersecurity study materials and generate practice quizzes powered by RAG")

if col.count() == 0:
    st.warning("Upload some study materials using the sidebar first!")
else:
    c1, c2 = st.columns([3, 1])
    topic = c1.text_input("Topic to quiz on",
                          placeholder="e.g. network security, encryption...")
    num_q = c2.slider("Questions", 1, 15, 5)

    if st.button("Generate Quiz", type="primary", disabled=not topic):
        with st.spinner("Generating quiz..."):
            try:
                st.session_state.quiz_data = generate_quiz(topic, num_q)
                st.session_state.quiz_submitted = False
                st.session_state.quiz_results = None
                st.session_state.user_answers = {}
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # ---- show quiz questions ----
    if st.session_state.quiz_data and not st.session_state.quiz_submitted:
        questions = st.session_state.quiz_data.get("questions", [])
        st.divider()
        for i, q in enumerate(questions):
            st.markdown(f"**Q{i+1}. {q['question']}**")
            opts = [f"{k}: {v}" for k, v in q["options"].items()]
            choice = st.radio(f"Q{i+1}", opts, key=f"q_{i}",
                              index=None, label_visibility="collapsed")
            if choice:
                st.session_state.user_answers[i] = choice.split(":")[0].strip()
            st.markdown("---")

        if st.button("Submit Answers", type="primary"):
            if len(st.session_state.user_answers) < len(questions):
                st.warning("Answer all questions first!")
            else:
                result = grade_quiz(questions, st.session_state.user_answers)
                st.session_state.quiz_results = result
                st.session_state.quiz_submitted = True
                st.rerun()

    # ---- show results after submission ----
    if st.session_state.quiz_submitted and st.session_state.quiz_results:
        r = st.session_state.quiz_results
        questions = st.session_state.quiz_data["questions"]
        st.divider()

        color = "#28a745" if r["score"] >= 80 else "#ffc107" if r["score"] >= 60 else "#dc3545"
        st.markdown(
            f'<div style="padding:20px;border-radius:10px;text-align:center;'
            f'font-size:1.5rem;font-weight:bold;background:{color}22;color:{color}">'
            f'{r["correct"]}/{r["total"]} ({r["score"]:.0f}%)</div>',
            unsafe_allow_html=True)

        for i, q in enumerate(questions):
            with st.expander(f"Q{i+1}. {q['question']}", expanded=True):
                ans = st.session_state.user_answers.get(i)
                if ans == q["correct"]:
                    st.success(f"✅ Your answer: {ans} (Correct!)")
                else:
                    st.error(f"❌ Your answer: {ans} | Correct: {q['correct']}")
                st.info(f"💡 {q['explanation']}")

        c1, c2 = st.columns(2)
        if c1.button("🔄 Retake"):
            st.session_state.quiz_submitted = False
            st.session_state.quiz_results = None
            st.session_state.user_answers = {}
            st.rerun()
        if c2.button("✨ New Quiz"):
            st.session_state.quiz_data = None
            st.session_state.quiz_submitted = False
            st.session_state.user_answers = {}
            st.rerun()
