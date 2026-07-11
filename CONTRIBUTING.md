# Contributing to SmartCS

Thanks for helping improve SmartCS. The project is moving toward a clean, demo-friendly, contributor-friendly AI customer-service workbench.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

For a fast local loop, set these values in `.env`:

```env
SOCKETIO_ASYNC_MODE=threading
LOAD_EMOTION_MODEL_ON_STARTUP=false
ENABLE_DEMO_SEED=true
DEMO_ADMIN_PASSWORD=admin12345
DEMO_USER_PASSWORD=user12345
```

Run setup helpers when needed:

```powershell
$env:FLASK_APP="wsgi:app"
flask smartcs init-db
flask smartcs seed-demo
flask smartcs check-models
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Contribution Priorities

High-impact areas:

- Documentation, screenshots, demo GIFs, and quick-start reliability.
- Splitting `smartcs/legacy_app.py` into Blueprints and services.
- Tests for routes, services, Socket.IO events, and security boundaries.
- RAG knowledge-base improvements.
- LLM provider adapters.
- Accessibility and mobile polish for the UI.

## Coding Guidelines

- Keep public URLs and JSON response shapes stable unless the change is explicitly breaking.
- Prefer small, focused modules over adding more logic to `legacy_app.py`.
- Keep fallback behavior working when `LLM_API_KEY` is empty and the BERT model is not loaded.
- Add or update tests for behavior changes.
- Do not commit `.env`, databases, logs, cache files, or large model binaries.

## Pull Request Checklist

Before opening a PR:

- [ ] Tests pass locally.
- [ ] Documentation is updated when behavior or setup changes.
- [ ] New environment variables are added to `.env.example`.
- [ ] Security-sensitive changes are called out in the PR description.
- [ ] Screenshots or GIFs are included for visible UI changes.

## Issue Labels

Suggested labels for maintainers:

- `good first issue`
- `help wanted`
- `bug`
- `docs`
- `security`
- `architecture`
- `frontend`
- `ai`

