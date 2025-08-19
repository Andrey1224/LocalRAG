# Code Quality Analysis: What's Wrong with Legacy Code

## 🔍 **Основные проблемы в коде LocalRAG**

### 1. **B904 - Неправильная обработка исключений**

#### ❌ Проблема в коде:
```python
# app/api/ask.py:191-197
except Exception as e:
    logger.error("Question processing failed", error=str(e))
    if "timeout" in error_msg:
        raise HTTPException(status_code=504, detail="Request timeout")  # Теряется original exception
    elif "model" in error_msg:
        raise HTTPException(status_code=503, detail="LLM service unavailable")  # Не видно причину
```

#### ✅ Правильный подход:
```python
except Exception as e:
    logger.error("Question processing failed", error=str(e))
    if "timeout" in error_msg:
        raise HTTPException(status_code=504, detail="Request timeout") from e  # Сохраняется chain
    elif "model" in error_msg:
        raise HTTPException(status_code=503, detail="LLM service unavailable") from e
```

**Почему важно:**
- Теряется information about original error
- Debugging становится сложнее
- Невозможно проследить причину проблемы

---

### 2. **F841 - Неиспользуемые переменные**

#### ❌ Проблема в коде:
```python
# app/api/health.py:37
collections = client.get_collections()  # Переменная создается, но не используется
return "healthy"

# app/api/health.py:146
critical_services = ["postgresql", "qdrant"]  # Объявлено, но не используется
```

#### ✅ Правильный подход:
```python
# Если результат нужен для проверки:
collections = client.get_collections()
if not collections:
    raise Exception("No collections found")

# Если результат не нужен:
client.get_collections()  # Просто вызов без присваивания

# Если переменная планируется к использованию:
_collections = client.get_collections()  # Префикс _ показывает "unused by design"
```

---

### 3. **B008 - Function calls в default arguments**

#### ❌ Проблема в коде:
```python
# app/api/evaluation.py:177
@router.post("/evaluate")
async def evaluate_answer(
    request: EvaluationRequest,
    deps = Depends(get_dependencies)  # Вызов функции в default argument
):
```

#### ✅ Правильный подход:
```python
@router.post("/evaluate")  
async def evaluate_answer(
    request: EvaluationRequest,
    deps = Depends(get_dependencies)  # Это OK - Depends() специально для этого
):

# Или для обычных функций:
def process_data(data: str, timestamp = None):
    if timestamp is None:
        timestamp = datetime.now()  # Вызов внутри функции
```

**Почему важно:**
- Default arguments вычисляются один раз при import
- Могут быть shared между вызовами функции
- В FastAPI Depends() это исключение, но linter этого не знает

---

### 4. **E402 - Imports не в начале файла**

#### ❌ Проблема в коде:
```python
# app/services/chunking.py:190
def some_function():
    # код...

import tiktoken  # Import внутри функции или после кода
```

#### ✅ Правильный подход:
```python
# Все imports в начале файла
import tiktoken
from typing import List

def some_function():
    # код...
```

---

### 5. **UP007 - Старый синтаксис типов**

#### ❌ Проблема в коде:
```python
# app/core/logging.py:129
from typing import Union, Optional

def log_event(data: Union[str, dict]) -> Optional[str]:
    pass
```

#### ✅ Правильный подход (Python 3.10+):
```python
def log_event(data: str | dict) -> str | None:
    pass
```

---

### 6. **E501 - Слишком длинные строки**

#### ❌ Проблема в коде:
```python
# app/api/feedback.py:258
very_long_variable_name = "This is a very long string that exceeds the 100 character limit configured in our project settings"
```

#### ✅ Правильный подход:
```python
very_long_variable_name = (
    "This is a very long string that exceeds the 100 character limit "
    "configured in our project settings"
)
```

---

## 🎯 **Почему эти проблемы важны?**

### 1. **Maintainability**
- Код становится сложнее читать и понимать
- Debugging занимает больше времени
- Новые разработчики медленнее вникают

### 2. **Reliability** 
- Неправильная обработка ошибок скрывает проблемы
- Неиспользуемые переменные могут указывать на logic errors
- Старый синтаксис может быть deprecated

### 3. **Performance**
- Function calls в defaults могут вызывать неожиданное поведение
- Неиспользуемые imports увеличивают startup time

### 4. **Team Collaboration**
- Consistent code style облегчает code reviews
- Автоматическое форматирование предотвращает merge conflicts
- Linting rules помогают избежать common mistakes

---

## 🔧 **Стратегия исправления**

### Приоритет 1 (Critical):
- ✅ **B904**: Exception handling - влияет на debugging
- ✅ **F841**: Unused variables - может скрывать bugs

### Приоритет 2 (Important):  
- ✅ **E402**: Import order - affects readability
- ✅ **E501**: Line length - affects readability

### Приоритет 3 (Nice to have):
- ✅ **UP007**: Type syntax - modernization
- ✅ **B008**: Default arguments - potential issues

---

## 🚀 **Что уже сделано**

1. **Временные игнор-правила** для плавного перехода
2. **Документация** с примерами исправлений
3. **Pre-commit хуки** для предотвращения новых проблем
4. **Автоматическое форматирование** (Black, Prettier)

**Результат:** Новый код автоматически соответствует стандартам, legacy код исправляется постепенно.