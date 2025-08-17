"""Simple Streamlit UI for LocalRAG (placeholder for now)."""

import streamlit as st

st.set_page_config(
    page_title="LocalRAG",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 LocalRAG Assistant")
st.markdown("*LLM-платформа с RAG и обратной связью*")

st.info("🚧 UI in development. API is available at http://localhost:8000")

# Basic health check
st.markdown("### System Status")
st.markdown("- ✅ Streamlit UI: Running")
st.markdown("- 🔄 API: Check http://localhost:8000/healthz")
st.markdown("- 📚 Documentation: http://localhost:8000/docs")