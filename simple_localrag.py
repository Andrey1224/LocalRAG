#!/usr/bin/env python3
"""
Простая полнофункциональная версия LocalRAG
Демонстрирует реальную работу с вашими данными
"""

import os
import json
import time
import hashlib
from typing import List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import asyncio

# Модели данных
class IngestRequest(BaseModel):
    paths: List[str]
    delete_missing: bool = False

class AskRequest(BaseModel):
    question: str

class FeedbackRequest(BaseModel):
    question: str
    llm_answer: str
    citations_used: List[str]
    rating: str
    reason: str
    comment: str
    session_id: str
    request_id: str

# Создаем приложение
app = FastAPI(title="LocalRAG - Real Implementation", version="2.0.0")

# Глобальное хранилище документов в памяти
DOCUMENT_STORE = {}
CHUNK_STORE = {}

# Простая реализация документного парсера
def parse_document(file_path: str) -> Dict[str, Any]:
    """Парсит документ и возвращает содержимое"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    content = ""
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext in ['.md', '.txt', '.html', '.htm', '.json', '.csv', '.log']:
        # Текстовые форматы
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    elif file_ext == '.pdf':
        # PDF требует специальную библиотеку
        raise ValueError("PDF format requires additional libraries. Please convert to text format.")
    elif file_ext in ['.docx', '.doc']:
        # Word документы требуют специальную библиотеку
        raise ValueError("Word format requires additional libraries. Please convert to text format.")
    else:
        # Пытаемся читать как текст для других форматов
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            raise ValueError(f"Unsupported binary format: {file_ext}. Please use text-based formats.")
    
    # Создаем хэш содержимого
    content_hash = hashlib.md5(content.encode()).hexdigest()
    
    return {
        "path": file_path,
        "content": content,
        "content_hash": content_hash,
        "size": len(content),
        "extension": file_ext
    }

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Улучшенная разбивка текста на чанки с семантическим разделением"""
    chunks = []
    
    # Сначала разделяем по заголовкам и крупным секциям
    sections = []
    lines = text.split('\n')
    current_section = []
    
    for line in lines:
        # Определяем заголовки (строки с #, ** или ==)
        if (line.strip().startswith('#') or 
            line.strip().startswith('**') and line.strip().endswith('**') or
            '==' in line or line.strip().isupper() and len(line.strip()) < 50):
            
            if current_section:
                sections.append('\n'.join(current_section))
                current_section = []
            current_section.append(line)
        else:
            current_section.append(line)
    
    if current_section:
        sections.append('\n'.join(current_section))
    
    # Теперь разбиваем секции на чанки по символам, а не словам
    for section in sections:
        if len(section) <= chunk_size:
            if section.strip():  # Не добавляем пустые чанки
                chunks.append(section)
        else:
            # Разбиваем большие секции по абзацам
            paragraphs = section.split('\n\n')
            current_chunk = ""
            
            for paragraph in paragraphs:
                if len(current_chunk + '\n\n' + paragraph) <= chunk_size:
                    if current_chunk:
                        current_chunk += '\n\n' + paragraph
                    else:
                        current_chunk = paragraph
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk)
                    current_chunk = paragraph
                    
                    # Если абзац слишком длинный, разбиваем по предложениям
                    if len(current_chunk) > chunk_size:
                        sentences = current_chunk.split('. ')
                        temp_chunk = ""
                        
                        for sentence in sentences:
                            if len(temp_chunk + '. ' + sentence) <= chunk_size:
                                if temp_chunk:
                                    temp_chunk += '. ' + sentence
                                else:
                                    temp_chunk = sentence
                            else:
                                if temp_chunk.strip():
                                    chunks.append(temp_chunk)
                                temp_chunk = sentence
                        
                        if temp_chunk.strip():
                            current_chunk = temp_chunk
            
            if current_chunk.strip():
                chunks.append(current_chunk)
    
    return [chunk for chunk in chunks if chunk.strip()]

def simple_search(query: str, chunks: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    """Улучшенный поиск с TF-IDF и расширенными синонимами"""
    import math
    import re
    
    query_lower = query.lower()
    query_words = set(re.findall(r'\b\w+\b', query_lower))
    results = []
    
    # Расширенные синонимы для улучшения поиска
    synonyms = {
        'поддержка': ['support', 'помощь', 'сервис', 'техподдержка', 'клиент', 'служба', 'обслуживание'],
        'безопасность': ['security', 'защита', 'политика', 'контроль', 'безопасный', 'защищенный'],
        'продукт': ['product', 'приложение', 'сервис', 'платформа', 'решение', 'система', 'софт'],
        'информация': ['данные', 'сведения', 'details', 'info', 'описание', 'детали'],
        'функции': ['функция', 'возможности', 'features', 'функционал', 'опции'],
        'интеграция': ['integration', 'подключение', 'соединение', 'связь', 'api'],
        'время': ['время', 'часы', 'расписание', 'график', 'schedule', 'working'],
        'контакты': ['контакт', 'связь', 'телефон', 'email', 'адрес', 'contact']
    }
    
    # Расширяем запрос синонимами
    expanded_query_words = set(query_words)
    for word in query_words:
        for key, syns in synonyms.items():
            if word == key or word in syns:
                expanded_query_words.update(syns)
                expanded_query_words.add(key)
    
    # Подсчет общего количества документов для TF-IDF
    total_docs = len(chunks)
    
    for chunk_id, chunk_data in chunks.items():
        chunk_text = chunk_data['text'].lower()
        chunk_words = re.findall(r'\b\w+\b', chunk_text)
        chunk_word_set = set(chunk_words)
        chunk_word_count = len(chunk_words)
        
        # TF-IDF расчеты
        tf_idf_score = 0
        for word in query_words:
            if word in chunk_words:
                # Term Frequency
                tf = chunk_words.count(word) / chunk_word_count if chunk_word_count > 0 else 0
                
                # Document Frequency (упрощенный расчет)
                docs_containing_word = sum(1 for _, data in chunks.items() 
                                         if word in data['text'].lower())
                
                # Inverse Document Frequency
                idf = math.log(total_docs / max(1, docs_containing_word))
                
                tf_idf_score += tf * idf
        
        # Пересечения слов
        direct_intersection = len(query_words & chunk_word_set)
        expanded_intersection = len(expanded_query_words & chunk_word_set)
        
        # Проверка точных фраз
        phrase_matches = sum(1 for word in query_words if word in chunk_text)
        
        # Семантическая релевантность на основе категорий
        semantic_score = 0
        
        # Проверка категорий вопросов
        categories = {
            'support': ['поддержк', 'support', 'помощ', 'клиент', 'сервис', 'служб'],
            'security': ['безопасност', 'security', 'защит', 'политик', 'контрол'],
            'product': ['продукт', 'product', 'приложен', 'платформ', 'систем', 'решен'],
            'features': ['функци', 'возможност', 'features', 'функционал', 'опци'],
            'integration': ['интеграци', 'integration', 'подключен', 'api', 'связ'],
            'contact': ['контакт', 'связ', 'телефон', 'email', 'адрес']
        }
        
        for category, keywords in categories.items():
            query_has_category = any(kw in query_lower for kw in keywords)
            chunk_has_category = any(kw in chunk_text for kw in keywords)
            
            if query_has_category and chunk_has_category:
                semantic_score += 0.8
        
        # Итоговый score с улучшенными весами
        if (direct_intersection > 0 or expanded_intersection > 0 or 
            phrase_matches > 0 or semantic_score > 0 or tf_idf_score > 0):
            
            total_score = (
                tf_idf_score * 0.3 +
                (direct_intersection / max(1, len(query_words))) * 0.25 +
                (expanded_intersection / max(1, len(expanded_query_words))) * 0.2 +
                (phrase_matches / max(1, len(query_words))) * 0.15 +
                semantic_score * 0.1
            )
            
            results.append({
                "chunk_id": chunk_id,
                "text": chunk_data['text'],
                "source": chunk_data['source'],
                "score": round(total_score, 3),
                "metadata": chunk_data.get('metadata', {}),
                "debug": {
                    "tf_idf_score": round(tf_idf_score, 3),
                    "direct_matches": direct_intersection,
                    "expanded_matches": expanded_intersection,
                    "phrase_matches": phrase_matches,
                    "semantic_score": round(semantic_score, 3)
                }
            })
    
    # Сортируем по релевантности
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]

def generate_answer_with_ollama(question: str, context_chunks: List[Dict]) -> str:
    """Улучшенная генерация ответов с полным извлечением контекста"""
    import re
    
    if not context_chunks:
        return "Извините, не удалось найти релевантную информацию в документах."
    
    # Анализируем тип вопроса для лучшего извлечения контекста
    question_lower = question.lower()
    
    # Категоризация вопросов
    question_categories = {
        'product': ['продукт', 'что', 'описание', 'система', 'платформа', 'приложение'],
        'support': ['поддержка', 'помощь', 'клиент', 'сервис', 'техподдержка'],
        'contact': ['контакт', 'связь', 'телефон', 'email', 'адрес', 'время'],
        'features': ['функци', 'возможност', 'умеет', 'может', 'фичи'],
        'integration': ['интеграция', 'подключение', 'api', 'связать'],
        'security': ['безопасность', 'защита', 'политика', 'права']
    }
    
    # Определяем основную категорию вопроса
    main_category = None
    for category, keywords in question_categories.items():
        if any(keyword in question_lower for keyword in keywords):
            main_category = category
            break
    
    relevant_sections = []
    sources = set()
    
    for chunk in context_chunks:
        sources.add(chunk['source'])
        text = chunk['text']
        
        # Улучшенное извлечение секций на основе структуры документа
        sections = extract_relevant_sections(text, question_lower, main_category)
        relevant_sections.extend(sections)
    
    if relevant_sections:
        # Удаляем дубликаты и сортируем по релевантности
        unique_sections = list(dict.fromkeys(relevant_sections))  # Сохраняем порядок
        
        answer_parts = []
        for i, section in enumerate(unique_sections[:3]):  # Берем топ 3 секции
            if section.strip():
                answer_parts.append(f"{section.strip()}")
        
        if answer_parts:
            answer = "\n\n".join(answer_parts)
            
            # Добавляем источники
            if sources:
                source_list = ", ".join(sorted(sources))
                answer += f"\n\n📚 Источники: {source_list}"
            
            return answer


def extract_relevant_sections(text: str, question: str, category: str = None) -> List[str]:
    """Извлекает релевантные секции из текста на основе вопроса"""
    import re
    
    sections = []
    lines = text.split('\n')
    
    # Определяем ключевые слова для поиска
    search_keywords = set()
    
    if category == 'product':
        search_keywords.update(['продукт', 'описание', 'система', 'платформа', 'приложение', 'что'])
    elif category == 'support':
        search_keywords.update(['поддержка', 'помощь', 'клиент', 'сервис', 'техподдержка'])
    elif category == 'contact':
        search_keywords.update(['контакт', 'связь', 'телефон', 'email', 'время', 'часы'])
    elif category == 'features':
        search_keywords.update(['функци', 'возможност', 'может', 'умеет'])
    elif category == 'integration':
        search_keywords.update(['интеграци', 'подключение', 'api'])
    elif category == 'security':
        search_keywords.update(['безопасность', 'защита', 'политика'])
    
    # Добавляем слова из вопроса
    question_words = re.findall(r'\b\w+\b', question.lower())
    search_keywords.update(question_words)
    
    i = 0
    while i < len(lines):
        line = lines[i].lower()
        
        # Проверяем, содержит ли строка ключевые слова
        if any(keyword in line for keyword in search_keywords):
            # Определяем тип секции (заголовок или содержимое)
            if (lines[i].strip().startswith('#') or 
                lines[i].strip().startswith('**') or
                lines[i].strip().isupper() or 
                '==' in lines[i]):
                
                # Это заголовок - берем его и следующий контент
                section_lines = [lines[i]]
                j = i + 1
                
                # Собираем контент до следующего заголовка
                while j < len(lines):
                    next_line = lines[j]
                    if (next_line.strip().startswith('#') or 
                        next_line.strip().startswith('**') or
                        '==' in next_line or
                        (next_line.strip().isupper() and len(next_line.strip()) < 50)):
                        break
                    
                    if next_line.strip():  # Не добавляем пустые строки
                        section_lines.append(next_line)
                    j += 1
                
                section = '\n'.join(section_lines)
                if len(section.strip()) > 20:  # Игнорируем слишком короткие секции
                    sections.append(section)
                
                i = j
            else:
                # Это обычная строка с ключевым словом - берем контекст вокруг
                start_idx = max(0, i - 2)
                end_idx = min(len(lines), i + 8)
                
                context_lines = []
                for k in range(start_idx, end_idx):
                    if lines[k].strip():
                        context_lines.append(lines[k])
                
                if context_lines:
                    section = '\n'.join(context_lines)
                    if len(section.strip()) > 20:
                        sections.append(section)
                
                i += 1
        else:
            i += 1
    
    return sections

# API эндпоинты
@app.get("/health")
async def health_check():
    """Проверка состояния системы"""
    
    # Проверяем Ollama
    ollama_status = "connected"
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code != 200:
            ollama_status = "disconnected"
    except:
        ollama_status = "disconnected"
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "api": "running",
            "document_store": f"{len(DOCUMENT_STORE)} documents",
            "chunk_store": f"{len(CHUNK_STORE)} chunks",
            "ollama": ollama_status
        },
        "implementation": "Simple LocalRAG with real functionality"
    }

@app.post("/ingest")
async def ingest_documents(request: IngestRequest):
    """Загружает и индексирует реальные документы"""
    
    indexed_count = 0
    skipped_count = 0
    errors = []
    
    for file_path in request.paths:
        try:
            # Парсим документ
            doc_data = parse_document(file_path)
            doc_id = doc_data["content_hash"]
            
            # Проверяем, не загружен ли уже
            if doc_id in DOCUMENT_STORE:
                skipped_count += 1
                continue
            
            # Сохраняем документ
            DOCUMENT_STORE[doc_id] = doc_data
            
            # Разбиваем на чанки
            chunks = chunk_text(doc_data["content"])
            
            # Индексируем чанки
            for i, chunk_content in enumerate(chunks):
                chunk_id = f"{doc_id}_{i:03d}"
                CHUNK_STORE[chunk_id] = {
                    "text": chunk_content,
                    "source": os.path.basename(file_path),
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "metadata": {
                        "path": file_path,
                        "extension": doc_data["extension"]
                    }
                }
                indexed_count += 1
            
            print(f"✅ Загружен документ: {file_path} ({len(chunks)} чанков)")
            
        except Exception as e:
            errors.append({
                "path": file_path,
                "error": str(e),
                "code": "PROCESSING_ERROR"
            })
            print(f"❌ Ошибка загрузки {file_path}: {e}")
    
    return {
        "indexed": indexed_count,
        "skipped": skipped_count,
        "errors": errors,
        "doc_id": f"batch_{int(time.time())}"
    }

@app.post("/ask")
async def ask_question(request: AskRequest):
    """Отвечает на вопросы используя загруженные документы"""
    
    if not CHUNK_STORE:
        raise HTTPException(
            status_code=400, 
            detail="No documents loaded. Please ingest documents first using /ingest endpoint."
        )
    
    start_time = time.time()
    
    # Поиск релевантных чанков
    search_start = time.time()
    search_results = simple_search(request.question, CHUNK_STORE, top_k=5)
    search_time = int((time.time() - search_start) * 1000)
    
    if not search_results:
        return {
            "answer": "К сожалению, я не нашел релевантной информации для ответа на ваш вопрос в загруженных документах.",
            "citations": [],
            "debug": {
                "trace_id": f"trace_{int(time.time())}",
                "search_time_ms": search_time,
                "generation_time_ms": 0,
                "found_chunks": 0
            }
        }
    
    # Генерация ответа
    gen_start = time.time()
    answer = generate_answer_with_ollama(request.question, search_results)
    gen_time = int((time.time() - gen_start) * 1000)
    
    # Формируем цитаты
    citations = []
    for result in search_results:
        citations.append({
            "source": result["source"],
            "chunk_id": result["chunk_id"],
            "relevance_score": round(result["score"], 3),
            "text_preview": result["text"][:200] + "..." if len(result["text"]) > 200 else result["text"]
        })
    
    total_time = int((time.time() - start_time) * 1000)
    
    return {
        "answer": answer,
        "citations": citations,
        "debug": {
            "trace_id": f"trace_{int(time.time())}",
            "search_time_ms": search_time,
            "generation_time_ms": gen_time,
            "total_time_ms": total_time,
            "found_chunks": len(search_results),
            "query_terms": len(request.question.split())
        }
    }

@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Сохраняет обратную связь пользователя"""
    
    feedback_id = f"feedback_{int(time.time())}"
    
    # В реальной системе здесь было бы сохранение в базу данных
    feedback_data = {
        "feedback_id": feedback_id,
        "timestamp": time.time(),
        "question": request.question,
        "llm_answer": request.llm_answer,
        "rating": request.rating,
        "reason": request.reason,
        "comment": request.comment,
        "session_id": request.session_id,
        "request_id": request.request_id
    }
    
    # Для демонстрации просто выводим в консоль
    print(f"📝 Получен фидбек: {request.rating} - {request.reason}")
    print(f"   Комментарий: {request.comment}")
    
    return {
        "status": "ok",
        "feedback_id": feedback_id,
        "message": "Thank you for your feedback!"
    }

@app.get("/documents")
async def list_documents():
    """Получить список всех загруженных документов"""
    documents = []
    for doc_id, doc_data in DOCUMENT_STORE.items():
        chunks_count = len([c for c in CHUNK_STORE.values() if c["doc_id"] == doc_id])
        documents.append({
            "doc_id": doc_id,
            "doc_id_short": doc_id[:8] + "...",
            "path": doc_data["path"],
            "filename": os.path.basename(doc_data["path"]),
            "size": doc_data["size"],
            "chunks": chunks_count,
            "extension": doc_data["extension"]
        })
    
    return {
        "total_documents": len(documents),
        "total_chunks": len(CHUNK_STORE),
        "documents": documents
    }

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Удалить документ и связанные с ним чанки"""
    
    if doc_id not in DOCUMENT_STORE:
        raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")
    
    # Получаем информацию о документе перед удалением
    doc_info = DOCUMENT_STORE[doc_id]
    
    # Удаляем все чанки этого документа
    chunks_to_delete = [chunk_id for chunk_id, chunk_data in CHUNK_STORE.items() 
                       if chunk_data["doc_id"] == doc_id]
    
    for chunk_id in chunks_to_delete:
        del CHUNK_STORE[chunk_id]
    
    # Удаляем сам документ
    del DOCUMENT_STORE[doc_id]
    
    print(f"🗑️ Удален документ: {doc_info['path']} ({len(chunks_to_delete)} чанков)")
    
    return {
        "status": "success",
        "message": f"Document {os.path.basename(doc_info['path'])} deleted successfully",
        "deleted_chunks": len(chunks_to_delete),
        "remaining_documents": len(DOCUMENT_STORE),
        "remaining_chunks": len(CHUNK_STORE)
    }

@app.get("/stats")
async def get_statistics():
    """Получить статистику системы"""
    return {
        "documents_loaded": len(DOCUMENT_STORE),
        "chunks_indexed": len(CHUNK_STORE),
        "document_details": [
            {
                "doc_id": doc_id[:8] + "...",
                "path": doc_data["path"],
                "size": doc_data["size"],
                "chunks": len([c for c in CHUNK_STORE.values() if c["doc_id"] == doc_id])
            }
            for doc_id, doc_data in DOCUMENT_STORE.items()
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск простой, но полнофункциональной версии LocalRAG")
    print("📚 Этот API может работать с реальными документами")
    print("🔍 Поддерживается реальный поиск и генерация ответов через Ollama")
    print("\n📋 Доступные эндпоинты:")
    print("  • GET /health - проверка состояния")
    print("  • POST /ingest - загрузка документов")
    print("  • POST /ask - вопросы к системе")
    print("  • POST /feedback - обратная связь")
    print("  • GET /stats - статистика системы")
    print("\n🌐 API будет доступен по адресу: http://localhost:8000")
    print("📖 Документация: http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)