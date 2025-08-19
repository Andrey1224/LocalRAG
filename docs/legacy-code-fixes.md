# Legacy Code Fixes for Pre-commit Compliance

## Overview
This document tracks legacy code issues identified by pre-commit hooks and their fixes.

## Current Issues Found

### 🔧 Ruff Linting Issues

#### B904 - Exception handling without `from`
**Issue:** `Within an except clause, raise exceptions with raise ... from err`
**Files:** Multiple API files
**Fix:** Add `from err` or `from None` to exception handling

```python
# Before
except Exception:
    raise HTTPException(status_code=500, detail="Error")

# After
except Exception as err:
    raise HTTPException(status_code=500, detail="Error") from err
```

#### B008 - Function calls in default arguments
**Issue:** `Do not perform function call Depends in argument defaults`
**Files:** FastAPI endpoint files
**Fix:** Move Depends() calls inside function

```python
# Before
def endpoint(deps = Depends(get_dependency)):
    pass

# After
def endpoint(deps = None):
    if deps is None:
        deps = Depends(get_dependency)
```

#### E402 - Module level imports not at top
**Issue:** Imports after other code
**Fix:** Move all imports to top of file

#### F841 - Unused variables
**Issue:** Variables assigned but never used
**Fix:** Remove unused variables or prefix with `_`

#### UP007 - Use `X | Y` for type annotations
**Issue:** Using `Union[X, Y]` instead of `X | Y`
**Fix:** Update to Python 3.10+ union syntax

### 🔒 Bandit Security Issues
**Status:** Scanning only `app/` directory to reduce noise
**Action:** Review and fix security warnings in production code

### 🧪 MyPy Type Issues
**Status:** Basic configuration with `--ignore-missing-imports`
**Action:** Gradually add type hints to improve type safety

## Temporary Workarounds Applied

### Pre-commit Configuration
- Ruff: Ignoring B904, B008, E402, F841, UP007 temporarily
- Bandit: Scanning only app/ directory
- MyPy: Ignoring missing imports
- Pytest: Using venv activation for compatibility

### Future Improvements
1. **Gradual fixes:** Address one file at a time
2. **Remove ignore rules:** As code is fixed, remove from ignore list
3. **Add stricter rules:** Enable more checks as code quality improves
4. **Type coverage:** Increase MyPy strictness gradually

## How to Fix Legacy Code

### Step 1: Pick a file to fix
```bash
git status --porcelain | head -5  # Pick a modified file
```

### Step 2: Run checks on single file
```bash
ruff check app/api/health.py
mypy app/api/health.py
bandit app/api/health.py
```

### Step 3: Fix issues one by one
- Add proper exception handling
- Move imports to top
- Add type hints
- Remove unused variables

### Step 4: Test the fixes
```bash
pre-commit run --files app/api/health.py
pytest tests/unit/ -v
```

### Step 5: Commit incremental improvements
```bash
git add app/api/health.py
git commit -m "fix: resolve linting issues in health.py"
```

## Progress Tracking

- [ ] app/api/health.py
- [ ] app/api/ask.py
- [ ] app/api/feedback.py
- [ ] app/api/evaluation.py
- [ ] app/api/ingest.py
- [ ] app/core/logging.py
- [ ] app/services/ files

Target: Fix 1-2 files per week to gradually improve code quality.
