

---

````markdown
# 📊 PRD: Логгинг и мониторинг запросов

## tl;dr

Реализовать централизованный логгинг всех обращений к API: `/ask`, `/feedback`, `/eval/run`. Логи включают ключевые параметры запроса, тайминги, trace_id, статусы и ошибки. В dev-режиме логи доступны в stdout и лог-файле. В prod — ведётся файл с ротацией и возможностью экспорта в внешние системы (Sentry, Logtail, Prometheus).

---

## 🎯 Goals

### Бизнес-цели

- Иметь полную трассировку всех запросов и производительности системы.
- Упростить отладку и обнаружение ошибок.
- Подготовиться к масштабированию и продакшн-нагрузкам.

### Цели команды

- Видеть latency по каждому этапу пайплайна `/ask`.
- Ловить ошибки и исключения по trace_id.
- Считать агрегаты по количеству запросов, отзывов, ошибок.

---

## 🧠 Что логгируется

### Общие поля (везде):

- `timestamp`
- `trace_id` (UUIDv4)
- `session_id`, `user_id` (если есть)
- `IP`, `user_agent`

### Для /ask:

- `question`
- `llm_model`, `reranker`
- `latency_total`
- Подэтапы:
  - `bm25_time_ms`
  - `embedding_time_ms`
  - `rerank_time_ms`
  - `llm_response_time_ms`
- `status_code`

### Для /feedback:

- `request_id`
- `rating`, `reason`, `comment` (если есть)

### Для /eval/run:

- `eval_type`
- `num_cases`
- `total_eval_time_ms`
- `avg_case_time_ms`
- Ошибки по кейсам (если есть)

### Исключения:

- stacktrace
- уровень — ERROR
- trace_id

---

## ⚙️ Технические детали

- Используем Python `logging` модуль.
- Middleware логирует вход/выход каждого запроса.
- Формат: JSON-логгирование.

### Режимы:

| Режим | Поток логов | Файл | Детали |
|-------|-------------|------|--------|
| dev   | stdout + файл | `logs/dev.log` | Включает тело запроса/ответа |
| prod  | только файл | `logs/app.log` (ротация) | Без полного текста ответа |

### Ротация:

- Через `TimedRotatingFileHandler`
- Логи хранятся 7 дней
- Размер файла: max 10MB

---

## 🧾 Пример лога (dev)

```json
{
  "timestamp": "2025-08-16T12:00:00Z",
  "trace_id": "9df6a1f3...",
  "endpoint": "/ask",
  "question": "Какие меры безопасности в политике?",
  "llm_model": "llama3.1:8b",
  "latency_total_ms": 2840,
  "bm25_time_ms": 44,
  "embedding_time_ms": 130,
  "rerank_time_ms": 90,
  "llm_response_time_ms": 2000,
  "status_code": 200,
  "session_id": "sess_123",
  "user_agent": "Mozilla/5.0"
}
````

---

## 📈 Метрики (в будущем через Prometheus)

* `total_requests_per_day`
* `avg_latency_per_endpoint`
* `errors_by_type`
* `feedback_positive_ratio`
* `top_negative_reasons`

---

## 🔐 Безопасность

* Не логируем ответы целиком в проде.
* Маскируем:

  * IP (например, `***.***.1.12`)
  * Чувствительные поля (`tokens`, `emails`, `names`)
* В будущем: scrubber для GDPR / PII

---

## 🔁 Интеграции (будущее)

| Интеграция | Назначение             |
| ---------- | ---------------------- |
| Sentry     | Ошибки и трейсинг      |
| Logtail    | Удобный просмотр логов |
| Prometheus | Метрики и алерты       |
| Grafana    | Визуализация запросов  |

---

## 📆 Milestones

1. **Week 1** — Базовый логгинг всех запросов, trace\_id, latency
2. **Week 2** — Исключения, ротация логов, dev/prod режимы
3. **Week 3** — Прототип метрик, агрегаты
4. **Week 4** — Интеграция с внешним логгером (Sentry/Logtail)

---


