"""LocalRAG Streamlit UI - Complete interface for RAG system."""

import os
import time
from datetime import datetime

import requests
import streamlit as st

# Configure page
st.set_page_config(
    page_title="LocalRAG Assistant", page_icon="🤖", layout="wide", initial_sidebar_state="expanded"
)

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class LocalRAGUI:
    """Main UI class for LocalRAG interface."""

    def __init__(self):
        self.api_base = API_BASE_URL

        # Initialize session state
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "session_id" not in st.session_state:
            st.session_state.session_id = f"session_{int(time.time())}"

    def call_api(self, endpoint: str, method: str = "GET", data: dict = None) -> dict:
        """Make API call with error handling."""
        url = f"{self.api_base}{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, timeout=30)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            st.error("⏰ Request timeout - please try again")
            return {"error": "timeout"}
        except requests.exceptions.ConnectionError:
            st.error("🔌 Cannot connect to API server")
            return {"error": "connection"}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                st.error("🚫 Rate limit exceeded - please wait before trying again")
            else:
                st.error(f"❌ API Error: {e.response.status_code}")
            return {"error": f"http_{e.response.status_code}"}
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            return {"error": str(e)}

    def check_system_health(self) -> dict:
        """Check system health status."""
        health = self.call_api("/healthz")
        if "error" not in health:
            detailed_health = self.call_api("/health/detailed")
            if "error" not in detailed_health:
                health.update(detailed_health)
        return health

    def ask_question(self, question: str) -> dict:
        """Ask a question to the RAG system."""
        return self.call_api("/api/ask", "POST", {"question": question})

    def submit_feedback(self, feedback_data: dict) -> dict:
        """Submit user feedback."""
        return self.call_api("/api/feedback", "POST", feedback_data)

    def get_feedback_reasons(self) -> list[str]:
        """Get valid feedback reasons."""
        result = self.call_api("/api/feedback/reasons")
        if "error" not in result:
            return result.get("reasons", [])
        return ["галлюцинация", "не по теме", "неполный ответ"]

    def render_header(self):
        """Render page header."""
        st.title("🤖 LocalRAG Assistant")
        st.markdown("*Умный помощник для поиска по внутренним документам*")

        # System status in sidebar
        with st.sidebar:
            st.header("📊 Система")

            if st.button("🔄 Проверить статус"):
                with st.spinner("Проверка..."):
                    health = self.check_system_health()

                if "error" in health:
                    st.error("❌ API недоступен")
                else:
                    st.success("✅ Система работает")

                    if "services" in health:
                        st.markdown("**Сервисы:**")
                        for service, status in health["services"].items():
                            if "healthy" in status:
                                st.success(f"✅ {service}")
                            else:
                                st.error(f"❌ {service}")

    def render_question_interface(self):
        """Render question asking interface."""
        st.header("💬 Задать вопрос")

        # Question input
        question = st.text_area(
            "Введите ваш вопрос:",
            height=100,
            placeholder="Например: Какие требования к безопасности описаны в политике?",
        )

        col1, col2 = st.columns([1, 4])

        with col1:
            ask_button = st.button("🔍 Спросить", disabled=len(question.strip()) < 5)

        with col2:
            if len(question.strip()) < 5 and question.strip():
                st.warning("Вопрос должен содержать минимум 5 символов")

        if ask_button and question.strip():
            self.handle_question(question.strip())

    def handle_question(self, question: str):
        """Handle question submission and display response."""
        # Add question to messages
        st.session_state.messages.append(
            {"type": "question", "content": question, "timestamp": datetime.now()}
        )

        # Show spinner and call API
        with st.spinner("🤔 Думаю..."):
            response = self.ask_question(question)

        if "error" in response:
            st.error("Не удалось получить ответ. Попробуйте позже.")
            return

        # Add response to messages
        message_data = {
            "type": "answer",
            "content": response.get("answer", ""),
            "citations": response.get("citations", []),
            "debug": response.get("debug", {}),
            "timestamp": datetime.now(),
            "question": question,
        }

        st.session_state.messages.append(message_data)

        # Scroll to bottom (rerun to show new message)
        st.rerun()

    def render_message(self, message: dict, index: int):
        """Render a single message (question or answer)."""
        if message["type"] == "question":
            with st.chat_message("user"):
                st.write(message["content"])
                st.caption(f"🕐 {message['timestamp'].strftime('%H:%M:%S')}")

        elif message["type"] == "answer":
            with st.chat_message("assistant"):
                # Answer content
                st.write(message["content"])

                # Citations
                if message.get("citations"):
                    with st.expander("📚 Источники", expanded=False):
                        for i, citation in enumerate(message["citations"], 1):
                            st.markdown(
                                f"""
                            **{i}. {citation.get('doc_title', 'Unknown Document')}**
                            - Источник: `{citation.get('source', 'unknown')}`
                            - Страница: {citation.get('page', 'N/A')}
                            - Раздел: {citation.get('section', 'N/A') if citation.get('section') else 'N/A'}
                            """
                            )

                # Debug info
                debug = message.get("debug", {})
                if debug:
                    with st.expander("🔧 Debug информация", expanded=False):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.metric("Общее время", f"{debug.get('total_time_ms', 0):.0f} мс")
                            st.metric("Найдено результатов", debug.get("search_results_count", 0))
                            st.metric("После rerank", debug.get("reranked_results_count", 0))

                        with col2:
                            st.metric("BM25 поиск", f"{debug.get('bm25_time_ms', 0):.0f} мс")
                            st.metric("Vector поиск", f"{debug.get('dense_time_ms', 0):.0f} мс")
                            st.metric("Генерация", f"{debug.get('generation_time_ms', 0):.0f} мс")

                        st.caption(f"Trace ID: {debug.get('trace_id', 'N/A')}")

                # Feedback section
                st.markdown("---")
                self.render_feedback_form(message, index)

                st.caption(f"🕐 {message['timestamp'].strftime('%H:%M:%S')}")

    def render_feedback_form(self, message: dict, message_index: int):
        """Render feedback form for an answer."""
        st.markdown("**Оцените ответ:**")

        col1, col2, col3 = st.columns([1, 1, 3])

        feedback_key = f"feedback_{message_index}"

        with col1:
            thumbs_up = st.button("👍", key=f"up_{message_index}")

        with col2:
            thumbs_down = st.button("👎", key=f"down_{message_index}")

        # Handle feedback submission
        if thumbs_up:
            self.submit_message_feedback(message, "up", message_index)

        if thumbs_down:
            self.show_negative_feedback_form(message, message_index)

    def show_negative_feedback_form(self, message: dict, message_index: int):
        """Show detailed form for negative feedback."""
        st.markdown("**Почему ответ не понравился?**")

        reasons = self.get_feedback_reasons()

        with st.form(f"negative_feedback_{message_index}"):
            reason = st.selectbox("Выберите причину:", reasons)
            comment = st.text_area("Дополнительный комментарий (опционально):")

            if st.form_submit_button("Отправить отзыв"):
                self.submit_message_feedback(message, "down", message_index, reason, comment)

    def submit_message_feedback(
        self,
        message: dict,
        rating: str,
        message_index: int,
        reason: str = None,
        comment: str = None,
    ):
        """Submit feedback for a message."""
        feedback_data = {
            "question": message.get("question", ""),
            "llm_answer": message.get("content", ""),
            "citations_used": [c.get("chunk_id", "") for c in message.get("citations", [])],
            "rating": rating,
            "reason": reason,
            "comment": comment,
            "session_id": st.session_state.session_id,
            "request_id": message.get("debug", {}).get("trace_id"),
        }

        with st.spinner("Отправка отзыва..."):
            result = self.submit_feedback(feedback_data)

        if "error" not in result:
            st.success("✅ Спасибо за отзыв!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ Не удалось отправить отзыв")

    def render_chat_history(self):
        """Render chat history."""
        if not st.session_state.messages:
            st.info("👋 Привет! Задайте мне вопрос о ваших документах.")
            return

        # Render messages
        for i, message in enumerate(st.session_state.messages):
            self.render_message(message, i)

    def render_sidebar(self):
        """Render sidebar with additional features."""
        with st.sidebar:
            st.header("⚙️ Настройки")

            # Clear chat button
            if st.button("🗑️ Очистить чат"):
                st.session_state.messages = []
                st.rerun()

            # Session info
            st.markdown("---")
            st.markdown("**Информация о сессии:**")
            st.caption(f"ID: {st.session_state.session_id}")
            st.caption(f"Сообщений: {len(st.session_state.messages)}")

            # API info
            st.markdown("---")
            st.markdown("**API:**")
            st.caption(f"URL: {self.api_base}")

            if st.button("📚 Открыть документацию"):
                st.link_button("📖 API Docs", f"{self.api_base}/docs")

    def run(self):
        """Main application runner."""
        self.render_header()
        self.render_sidebar()

        # Main content area
        st.markdown("---")

        # Chat interface
        chat_container = st.container()
        with chat_container:
            self.render_chat_history()

        # Question input at bottom
        st.markdown("---")
        self.render_question_interface()


# Run the application
if __name__ == "__main__":
    app = LocalRAGUI()
    app.run()
