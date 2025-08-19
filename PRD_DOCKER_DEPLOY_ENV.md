
---

````markdown
# 🐳 PRD: Docker / Deploy / ENV — инфраструктура и конфигурация проекта

## tl;dr

Реализовать полноценную обёртку для сборки, запуска и деплоя проекта с помощью Docker. Поддержка `.env`, `config.yaml`, multistage Dockerfile, docker-compose. Упор на dev/prod-разделение, лёгкий старт, и возможность деплоя на HuggingFace, Render, Railway, VPS, или облачные контейнерные платформы.

---

## 🎯 Goals

### Бизнес-цели

- Быстро разворачивать проект в dev/prod среде.
- Упростить доставку кода до заказчиков, клиентов, стейкхолдеров.
- Подготовить основу для CI/CD, тестов, хостинга и масштабирования.

### Цели команды

- Иметь стандартизированный Docker-контейнер.
- Поддерживать dev/prod окружения.
- Упаковать все зависимости, включая backend, UI и сторонние сервисы.

---

## 📂 Конфигурация

### Файлы:

- `.env`: переменные окружения
- `.env.example`: шаблон для разработчиков
- `config.yaml`: основные параметры (модели, лимиты, чанки и пр.)
- Используем `os.environ` + `pydantic.BaseSettings` для загрузки конфигов в коде

---

## 🐳 Docker

### Архитектура:

| Компонент | Назначение         |
|-----------|--------------------|
| app       | FastAPI backend    |
| ui        | Streamlit frontend |
| qdrant    | Векторный индекс   |
| ollama    | LLM runtime (локально) |
| minio     | (опционально) хранилище |

### docker-compose.yml

- Оркестрирует все сервисы.
- Поддерживает dev и prod версии через переменные.

### Dockerfile (multi-stage)

- Stage 1: установка зависимостей
- Stage 2: билд и запуск
- Упаковывает API и зависимости
- Автокеширование poetry.lock / requirements.txt

### Скрипты:

- `start.sh` — запуск в dev
- `entrypoint.sh` — настройка и запуск контейнера в проде

---

## 🚀 Деплой

### Target-платформы:

| Платформа            | Использование                        |
|----------------------|--------------------------------------|
| Hugging Face Spaces  | UI (Streamlit), быстрое MVP          |
| Render / Railway     | Backend (FastAPI)                    |
| Fly.io / VPS         | Полный стек в Docker                 |
| Replicate / Modal    | Опционально — генерация по API       |

### Зависимости:

- `pyproject.toml` + `poetry.lock` (предпочтительно)
- Автогенерация `requirements.txt` для Docker

---

## 🧪 Health-checks и тесты

- `/healthz` endpoint
- `self_check()` — проверка запуска моделей, подключений, индексов
- Тестовый скрипт: проверка latency и работоспособности `/ask`

---

## 🔁 CI/CD

### GitHub Actions:

- On push / pull_request
- Шаги:
  - `checkout`
  - `lint` (ruff/black)
  - `test` (pytest + coverage)
  - `docker build`
  - (опционально) push в Docker Hub

---

## 🧠 Окружения

| ENV   | Поведение                                       |
|--------|------------------------------------------------|
| `dev` | логгинг в stdout, отображение ответа, eval-режим |
| `prod`| логгинг в файл, отключение вывода ответа, маскирование ошибок |

Передаётся как `ENV=dev` в `.env`

---

## 🧾 Пример `.env.example`

```env
ENV=dev
API_HOST=0.0.0.0
API_PORT=8000
LLM_MODEL=llama3.1:8b
RERANKER_MODEL=bge-reranker-v2
MAX_TOKENS=400
DEBUG=True
````

---

## 🧩 config.yaml

```yaml
models:
  llm: llama3.1:8b
  reranker: bge-reranker-v2
limits:
  max_tokens: 400
  context_window: 2500
chunking:
  chunk_size: 1000
  overlap: 100
```

---

## 📆 Milestones

1. **Week 1** — Dockerfile, poetry, .env, базовый docker-compose
2. **Week 2** — Разделение на UI / API / Qdrant, healthz, self\_check
3. **Week 3** — CI/CD с GitHub Actions
4. **Week 4** — Поддержка prod-режима + хостинг (Render, HuggingFace)

---
