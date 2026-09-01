"""
Personal local dev tool for manually testing router.py / agent.py --
NOT the real product frontend (that's Sujal's scope in /frontend).
This exists purely so Vishvam can poke at the agent from a browser
instead of the REPL. Run with:

    streamlit run dev_ui/test_ui.py

Requires Ollama running locally (`ollama serve`) and all 4 models pulled.
"""

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "router"))

from agent import run  # noqa: E402

st.set_page_config(page_title="Agent Test UI (dev only)", layout="wide")
st.title("🛠️ Agent Test UI — internal dev tool")
st.caption(
    "Manual test harness for router.py / agent.py. Not the real product UI."
)

with st.sidebar:
    st.header("Query")
    query = st.text_area("Question", height=120, placeholder="e.g. Summarize this inspection report")
    uploaded_file = st.file_uploader(
        "Attach an image (optional)", type=["png", "jpg", "jpeg", "bmp", "tiff"]
    )
    user_id = st.text_input("user_id", value="dev-tester")
    run_button = st.button("Run agent", type="primary")

if uploaded_file is not None:
    st.sidebar.image(uploaded_file, caption="Attached image", use_container_width=True)

if run_button:
    if not query.strip():
        st.error("Enter a query first.")
    else:
        attachments = None
        if uploaded_file is not None:
            temp_dir = ROOT / "dev_ui" / "_uploads"
            temp_dir.mkdir(exist_ok=True)
            temp_path = temp_dir / uploaded_file.name
            temp_path.write_bytes(uploaded_file.getvalue())
            attachments = [str(temp_path)]

        with st.spinner("Running agent... (CPU inference can take 30-90s per step)"):
            t0 = time.time()
            try:
                result = run(query, user_id=user_id, attachments=attachments)
                elapsed = time.time() - t0
            except Exception as e:
                st.error(f"Agent run failed: {e}")
                st.stop()

        st.success(f"Done in {elapsed:.1f}s")

        st.subheader("Final Answer")
        st.markdown(result["final_answer"])

        st.subheader("Trace (what the system actually did)")
        for i, step in enumerate(result["trace"], 1):
            with st.expander(f"{i}. {step['step']}", expanded=True):
                detail = step["detail"]
                if isinstance(detail, (dict, list)):
                    st.json(detail)
                else:
                    st.write(detail)

        if result.get("files_to_generate"):
            st.subheader("Files to generate")
            st.json(result["files_to_generate"])
        else:
            st.caption("No files_to_generate for this query.")
