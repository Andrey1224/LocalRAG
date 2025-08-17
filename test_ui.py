#!/usr/bin/env python3
"""
Простой Streamlit UI для тестирования LocalRAG
"""

import streamlit as st
import requests
import json
import time
import os

# Конфигурация
API_BASE_URL = "http://localhost:8001"

st.set_page_config(
    page_title="LocalRAG Test UI",
    page_icon="🤖",
    layout="wide"
)

def main():
    st.title("🤖 LocalRAG Test Interface")
    st.write("Простой интерфейс для тестирования функциональности LocalRAG")
    
    # Боковое меню
    st.sidebar.title("Тестирование")
    mode = st.sidebar.selectbox(
        "Выберите режим тестирования:",
        ["Health Check", "File Upload", "Ingest Test", "Ask Test", "Document Management", "Feedback Test", "Full Test"]
    )
    
    if mode == "Health Check":
        test_health()
    elif mode == "File Upload":
        test_file_upload()
    elif mode == "Ingest Test":
        test_ingest()
    elif mode == "Ask Test":
        test_ask()
    elif mode == "Document Management":
        test_document_management()
    elif mode == "Feedback Test":
        test_feedback()
    elif mode == "Full Test":
        run_full_test()

def test_health():
    st.header("🔍 Health Check")
    
    if st.button("Проверить API"):
        with st.spinner("Проверяем API..."):
            try:
                response = requests.get(f"{API_BASE_URL}/health", timeout=10)
                if response.status_code == 200:
                    st.success("✅ API работает!")
                    st.json(response.json())
                else:
                    st.error(f"❌ API недоступен. Код: {response.status_code}")
            except Exception as e:
                st.error(f"❌ Ошибка соединения: {e}")

def test_file_upload():
    st.header("📁 Загрузка файлов")
    
    # Информация о поддерживаемых форматах
    st.info("""
    **📋 Поддерживаемые форматы:**
    - **Текстовые файлы**: .txt, .md (Markdown)
    - **Веб-форматы**: .html, .htm
    - **Данные**: .json, .csv, .log
    - **Другие текстовые форматы**: любые файлы с текстовым содержимым
    
    **📏 Ограничения:**
    - Максимальный размер файла: 50 МБ
    - Файлы должны быть в текстовом формате (UTF-8)
    - PDF и Word документы пока не поддерживаются (планируется в будущих версиях)
    """)
    
    # File uploader
    uploaded_files = st.file_uploader(
        "Выберите файлы для загрузки",
        type=['txt', 'md', 'html', 'htm', 'json', 'csv', 'log'],
        accept_multiple_files=True,
        help="Выберите один или несколько текстовых файлов для индексации в системе LocalRAG"
    )
    
    if uploaded_files:
        st.write(f"📎 Выбрано файлов: {len(uploaded_files)}")
        
        # Показываем информацию о файлах
        for file in uploaded_files:
            with st.expander(f"📄 {file.name} ({file.size} байт)"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Имя:** {file.name}")
                    st.write(f"**Размер:** {file.size:,} байт")
                    st.write(f"**Тип:** {file.type}")
                
                with col2:
                    # Предварительный просмотр содержимого
                    if file.size < 1000:  # Показываем превью для маленьких файлов
                        try:
                            content = file.read().decode('utf-8')
                            file.seek(0)  # Возвращаем указатель в начало
                            st.text_area("Превью", content[:200] + "..." if len(content) > 200 else content, height=100)
                        except:
                            st.write("Не удалось показать превью")
        
        # Кнопка загрузки
        if st.button("🚀 Загрузить файлы в систему", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            successful_uploads = []
            failed_uploads = []
            
            for i, file in enumerate(uploaded_files):
                status_text.text(f"Обрабатываем: {file.name}")
                progress_bar.progress((i + 1) / len(uploaded_files))
                
                try:
                    # Сохраняем файл временно
                    temp_path = f"/tmp/{file.name}"
                    with open(temp_path, "wb") as f:
                        f.write(file.read())
                    
                    # Загружаем через API
                    data = {
                        "paths": [temp_path],
                        "delete_missing": False
                    }
                    response = requests.post(
                        f"{API_BASE_URL}/ingest", 
                        json=data, 
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        successful_uploads.append({
                            "name": file.name,
                            "result": result
                        })
                    else:
                        failed_uploads.append({
                            "name": file.name,
                            "error": f"HTTP {response.status_code}: {response.text}"
                        })
                    
                    # Удаляем временный файл
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                        
                except Exception as e:
                    failed_uploads.append({
                        "name": file.name,
                        "error": str(e)
                    })
            
            progress_bar.progress(1.0)
            status_text.text("Загрузка завершена!")
            
            # Показываем результаты
            if successful_uploads:
                st.success(f"✅ Успешно загружено: {len(successful_uploads)} файлов")
                with st.expander("📊 Детали успешных загрузок"):
                    for upload in successful_uploads:
                        st.write(f"**{upload['name']}**: {upload['result']['indexed']} чанков проиндексировано")
            
            if failed_uploads:
                st.error(f"❌ Ошибки при загрузке: {len(failed_uploads)} файлов")
                with st.expander("⚠️ Детали ошибок"):
                    for upload in failed_uploads:
                        st.write(f"**{upload['name']}**: {upload['error']}")
            
            # Предложение перейти к тестированию
            if successful_uploads:
                st.info("💡 Теперь вы можете перейти в раздел 'Ask Test' для задания вопросов к загруженным документам!")

def test_ingest():
    st.header("📥 Тест загрузки документов")
    
    document_path = st.text_input(
        "Путь к документу:", 
        value="/Users/nepodymka/Desktop/LocalRAG/test_document.md"
    )
    
    if st.button("Загрузить документ"):
        if document_path:
            with st.spinner("Загружаем документ..."):
                try:
                    data = {
                        "paths": [document_path],
                        "delete_missing": False
                    }
                    response = requests.post(
                        f"{API_BASE_URL}/ingest", 
                        json=data, 
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success("✅ Документ загружен!")
                        st.json(result)
                    else:
                        st.error(f"❌ Ошибка: {response.status_code}")
                        st.text(response.text)
                        
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
        else:
            st.warning("Введите путь к документу")

def test_ask():
    st.header("❓ Тест вопросов")
    
    question = st.text_input(
        "Ваш вопрос:", 
        value="Какие меры безопасности описаны в политике?"
    )
    
    if st.button("Задать вопрос"):
        if question:
            with st.spinner("Ищем ответ..."):
                try:
                    data = {"question": question}
                    response = requests.post(
                        f"{API_BASE_URL}/ask", 
                        json=data, 
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success("✅ Ответ получен!")
                        
                        st.subheader("Ответ:")
                        st.write(result.get("answer", "Ответ не найден"))
                        
                        if "citations" in result:
                            st.subheader("Источники:")
                            for cite in result["citations"]:
                                st.write(f"- {cite}")
                        
                        if "debug" in result:
                            with st.expander("Debug информация"):
                                st.json(result["debug"])
                    else:
                        st.error(f"❌ Ошибка: {response.status_code}")
                        st.text(response.text)
                        
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
        else:
            st.warning("Введите вопрос")

def test_document_management():
    st.header("📚 Управление документами")
    
    # Добавляем состояние для автообновления
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = 0
    
    # Кнопки управления
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if st.button("🔄 Обновить список документов"):
            st.session_state.last_refresh += 1
            st.rerun()
    
    with col2:
        auto_refresh = st.checkbox("🔄 Автообновление", help="Обновлять список каждые 5 секунд")
    
    with col3:
        if st.button("🔍 Debug API"):
            st.info("Проверяем API напрямую...")
            debug_response = requests.get(f"{API_BASE_URL}/documents", timeout=10)
            st.json(debug_response.json() if debug_response.status_code == 200 else {"error": debug_response.status_code})
    
    if auto_refresh:
        time.sleep(1)  # Даем время на обновление
        st.rerun()
    
    try:
        # Получаем список документов
        response = requests.get(f"{API_BASE_URL}/documents", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            st.subheader(f"📊 Статистика")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Документов", data["total_documents"])
            with col2:
                st.metric("Чанков", data["total_chunks"])
            with col3:
                st.metric("Обновлений", st.session_state.last_refresh)
            
            # Показываем время последнего обновления
            st.caption(f"Последнее обновление: {time.strftime('%H:%M:%S')}")
            
            if data["documents"]:
                st.subheader("📝 Загруженные документы")
                
                for doc in data["documents"]:
                    with st.expander(f"📄 {doc['filename']} ({doc['size']} байт, {doc['chunks']} чанков)"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**Путь:** `{doc['path']}`")
                            st.write(f"**ID:** `{doc['doc_id_short']}`")
                            st.write(f"**Тип:** {doc['extension']}")
                            st.write(f"**Размер:** {doc['size']} байт")
                            st.write(f"**Чанков:** {doc['chunks']}")
                        
                        with col2:
                            if st.button(f"🗑️ Удалить", key=f"delete_{doc['doc_id']}"):
                                # Подтверждение удаления
                                if st.button(f"✅ Подтвердить удаление {doc['filename']}", key=f"confirm_{doc['doc_id']}"):
                                    with st.spinner("Удаляем документ..."):
                                        try:
                                            delete_response = requests.delete(
                                                f"{API_BASE_URL}/documents/{doc['doc_id']}", 
                                                timeout=10
                                            )
                                            
                                            if delete_response.status_code == 200:
                                                result = delete_response.json()
                                                st.success(f"✅ {result['message']}")
                                                st.write(f"Удалено чанков: {result['deleted_chunks']}")
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Ошибка удаления: {delete_response.status_code}")
                                                
                                        except Exception as e:
                                            st.error(f"❌ Ошибка: {e}")
            else:
                st.info("📭 Нет загруженных документов")
                st.write("Перейдите в раздел 'Ingest Test' для загрузки документов")
                
        else:
            st.error(f"❌ Ошибка получения списка документов: {response.status_code}")
            
    except Exception as e:
        st.error(f"❌ Ошибка соединения: {e}")

def test_feedback():
    st.header("📝 Тест обратной связи")
    
    col1, col2 = st.columns(2)
    
    with col1:
        question = st.text_input("Вопрос:", value="Тестовый вопрос")
        answer = st.text_area("Ответ:", value="Тестовый ответ")
        rating = st.selectbox("Оценка:", ["up", "down"])
    
    with col2:
        reason = st.selectbox("Причина:", [
            "полезный ответ", "неполный ответ", "галлюцинация", 
            "не по теме", "устаревшая информация"
        ])
        comment = st.text_area("Комментарий:", value="Тестовый комментарий")
    
    if st.button("Отправить обратную связь"):
        with st.spinner("Отправляем..."):
            try:
                data = {
                    "question": question,
                    "llm_answer": answer,
                    "citations_used": ["test_chunk"],
                    "rating": rating,
                    "reason": reason,
                    "comment": comment,
                    "session_id": "test_session",
                    "request_id": "test_request"
                }
                response = requests.post(
                    f"{API_BASE_URL}/feedback", 
                    json=data, 
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("✅ Обратная связь отправлена!")
                    st.json(result)
                else:
                    st.error(f"❌ Ошибка: {response.status_code}")
                    st.text(response.text)
                    
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

def run_full_test():
    st.header("🚀 Полное тестирование")
    
    if st.button("Запустить полный тест"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        tests = [
            ("Health Check", test_health_api),
            ("Document Ingest", test_ingest_api),
            ("Question Answering", test_ask_api),
            ("Feedback System", test_feedback_api)
        ]
        
        results = []
        
        for i, (test_name, test_func) in enumerate(tests):
            status_text.text(f"Выполняется: {test_name}")
            progress_bar.progress((i + 1) / len(tests))
            
            try:
                result = test_func()
                results.append((test_name, "✅ Успешно", result))
            except Exception as e:
                results.append((test_name, "❌ Ошибка", str(e)))
            
            time.sleep(1)
        
        status_text.text("Тестирование завершено!")
        
        st.subheader("Результаты тестирования:")
        for test_name, status, result in results:
            st.write(f"**{test_name}**: {status}")
            if isinstance(result, dict):
                with st.expander(f"Детали {test_name}"):
                    st.json(result)

def test_health_api():
    response = requests.get(f"{API_BASE_URL}/health", timeout=10)
    return response.json() if response.status_code == 200 else None

def test_ingest_api():
    data = {
        "paths": ["/Users/nepodymka/Desktop/LocalRAG/test_document.md"],
        "delete_missing": False
    }
    response = requests.post(f"{API_BASE_URL}/ingest", json=data, timeout=60)
    return response.json() if response.status_code == 200 else None

def test_ask_api():
    data = {"question": "Какие меры безопасности описаны в политике?"}
    response = requests.post(f"{API_BASE_URL}/ask", json=data, timeout=30)
    return response.json() if response.status_code == 200 else None

def test_feedback_api():
    data = {
        "question": "Тест",
        "llm_answer": "Тестовый ответ",
        "citations_used": ["test"],
        "rating": "up",
        "reason": "полезный ответ",
        "comment": "Тест",
        "session_id": "test",
        "request_id": "test"
    }
    response = requests.post(f"{API_BASE_URL}/feedback", json=data, timeout=30)
    return response.json() if response.status_code == 200 else None

if __name__ == "__main__":
    main()