PRD FILE

# 📘 PRD: API /ask — Поиск по внутренней документации с генерацией ответа

## tl;dr

Реализовать API-эндпоинт `/ask`, который принимает вопрос, выполняет гибридный поиск (BM25 + dense), переранжирует результаты с помощью cross-encoder, и генерирует краткий ответ через LLM с точными цитатами. Вся цепочка работает локально (Docker), с поддержкой логирования и трассировки (trace_id).

---

## 🎯 Goals

### Бизнес-цели

- Снизить нагрузку на сотрудников, отвечающих на повторяющиеся вопросы.
- Увеличить скорость доступа к знаниям из PDF, Markdown, HTML-документов.
- Создать базу для интеллектуального ассистента внутри компании.

### Цели пользователя

- Получить точный, краткий ответ.
- Видеть, откуда информация (цитата, источник, секция).
- Понимать, насколько система уверена в ответе.

### Не входит в задачи

- Ответы без источников.
- Многошаговое рассуждение, визуальные данные.
- UI, fine-tuning моделей.

---

## 👤 User Stories

- Как пользователь, я хочу ввести вопрос и получить конкретный ответ с цитатами.
- Как менеджер, я хочу доверять ответам, потому что вижу их источники.
- Как разработчик, я хочу дебажить и логировать каждый запрос (через trace_id).

---

## 🔁 User Flow

### POST /ask

**Запрос**:
```json
{
  "question": "Какой процесс утверждения бюджета?"
}

Обработка:

BM25-поиск по OpenSearch

Dense-поиск по Qdrant

Объединение и нормализация

Переранжировка cross-encoder’ом

Отбор лучших 5 фрагментов

Генерация ответа с цитатами через LLM

Возврат ответа с debug-данными

Ответ:

{
  "answer": "Процесс утверждения бюджета включает три этапа... [source: doc1, page 4]",
  "citations": [
    {
      "source": "doc1",
      "doc_title": "Финансовый регламент",
      "section": "Процесс утверждения",
      "page": 4
    }
  ],
  "debug": {
    "trace_id": "c3181d62-a5e6-4b45-9b10-d9acb4a7f8e3",
    "bm25_time_ms": 44,
    "dense_time_ms": 130,
    "rerank_time_ms": 90,
    "generation_time_ms": 2100,
    "confidence_score": 0.76
  }
}

📖 Narrative
Юристу нужно быстро понять, какие документы требуются для контракта. Он вводит вопрос, и система выдаёт короткий, проверяемый ответ с цитатой из нужного регламента. Он тратит секунды, а не часы. Такая система меняет подход к работе с корпоративными знаниями.

✅ Success Metrics
Ответ содержит минимум 1 цитату.

Время ответа ≤ 7 сек (CPU-only).

RAGAS:

faithfulness ≥ 0.65

answer_relevancy ≥ 0.60

Ручное тестирование: 8/10 успешных кейсов.

Юнит-тесты покрывают:

Индексы, reranker, генерация.
🧠 Technical Details
LLM: Ollama (llama3.1:8b или qwen2.5)

BM25: OpenSearch 2.x

Dense: Qdrant + BAAI/bge-small-en-v1.5

Reranker: BAAI/bge-reranker-v2-m3 via FlagEmbedding

FastAPI, Python 3.11+

Контейнеризация: Docker Compose

Limits:

Ответ: ≤ 400 токенов

Контекст: ≤ 2500 токенов

📆 Milestones
Week 1 — Индексы, базовый API

Week 2 — Объединение + rerank

Week 3 — Генерация через LLM

Week 4 — Debug + тесты

Week 5 — Eval + ручные проверки

Week 6 — Docker финализация

🧱 JSON-схемы
Запрос: POST /ask
{
  "type": "object",
  "properties": {
    "question": { "type": "string", "minLength": 5 }
  },
  "required": ["question"]
}

Ответ: 200 OK
{
  "type": "object",
  "properties": {
    "answer": { "type": "string" },
    "citations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": { "type": "string" },
          "doc_title": { "type": "string" },
          "section": { "type": "string" },
          "page": { "type": "integer" }
        },
        "required": ["source", "doc_title"]
      }
    },
    "debug": {
      "type": "object",
      "properties": {
        "trace_id": { "type": "string" },
        "bm25_time_ms": { "type": "number" },
        "dense_time_ms": { "type": "number" },
        "rerank_time_ms": { "type": "number" },
        "generation_time_ms": { "type": "number" },
        "confidence_score": { "type": "number" }
      }
    }
  },
  "required": ["answer", "citations"]
}

Ошибка: 4xx/5xx
{
  "type": "object",
  "properties": {
    "error": { "type": "string" },
    "code": {
      "type": "string",
      "enum": [
        "MISSING_QUESTION",
        "INVALID_QUESTION",
        "NO_RESULTS",
        "RERANKER_FAILED",
        "LLM_FAILED",
        "TIMEOUT",
        "UNKNOWN_ERROR"
      ]
    }
  },
  "required": ["error", "code"]
}

🚨 Edge-кейсы
Сценарий

Код

Код ошибки

Поведение

Нет question

400

MISSING_QUESTION

Вернуть ошибку

Вопрос < 5 символов

400

INVALID_QUESTION

Вернуть ошибку

Нет результатов

200

NO_RESULTS

Ответ: “Недостаточно данных”

Reranker упал

500

RERANKER_FAILED

Ответ с trace_id

LLM упал

500

LLM_FAILED

Ответ с trace_id

Таймаут > 10 сек

504

TIMEOUT

Ответ с trace_id

Ответ > 400 токенов

200

—

Ограничить max_tokens

🧠 System Prompt (LLM)
Ты ассистент, отвечающий на вопросы пользователя по внутренней документации. Ты всегда используешь только предоставленные фрагменты, не придумываешь ничего сам. В каждом ответе ты ОБЯЗАТЕЛЬНО вставляешь цитаты, указывая источник (source), название документа (doc_title), секцию или страницу (section/page).

Если информации недостаточно, ты честно отвечаешь: "Недостаточно данных для точного ответа."

Формат цитат: [source: doc1, page 4]

Говори кратко, ясно и точно.

