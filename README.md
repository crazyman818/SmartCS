# SmartCS

> Open-source AI customer service copilot for e-commerce teams.

SmartCS combines real-time customer chat, emotion-aware escalation, RAG knowledge-base answers, refund workflows, and an operator dashboard in a Flask application that can run locally without a paid LLM key.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-pytest-0A7F5A?logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Why SmartCS

Most AI customer-service demos stop at "chat with an LLM". SmartCS focuses on the operational loop around support teams:

- Emotion-aware routing: detects angry, sad, fearful, and high-risk messages, then escalates to human operators when needed.
- RAG customer-service answers: retrieves answers from a maintainable knowledge base, with keyword fallback when vector search is unavailable.
- Human-in-the-loop support: admins can monitor conversations, join rooms, send manual replies, and review intervention cases.
- E-commerce workflows: order lookup, refund requests, refund review, quick replies, and customer profile summaries.
- Operator analytics: message volume, satisfaction, emotion trends, intervention rates, refund workload, and exportable chat records.
- Local-first demo mode: runs with SQLite and fallback replies, so contributors can explore the system before configuring an LLM provider.

## Screenshots

Add current product screenshots before publishing the repository. See [docs/assets/README.md](docs/assets/README.md) for the expected asset list and capture guidance:

| Customer chat | Admin console | Dashboard |
| --- | --- | --- |
| `docs/assets/chat.png` | `docs/assets/admin-chat.png` | `docs/assets/dashboard.png` |

Recommended first release assets:

- 20-40 second GIF showing customer chat, AI reply, escalation, and admin intervention.
- Dashboard screenshot with seeded demo data.
- Architecture diagram showing browser, Flask, Socket.IO, services, SQLite, LLM provider, and optional BERT model.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Flask, Flask-SQLAlchemy, Flask-Login, Flask-SocketIO |
| AI reply | DeepSeek / OpenAI-compatible chat completions |
| Emotion recognition | PyTorch, Transformers, fine-tuned Chinese MacBERT, keyword fallback |
| RAG | Sentence-Transformers vector retrieval, keyword fallback |
| Frontend | Jinja2, vanilla JavaScript, Socket.IO, Chart.js |
| Database | SQLite by default, configurable through `DATABASE_URL` |
| Tests | pytest, pytest-cov |

## Quick Start

### Option A: Local Python

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

For a lightweight demo without loading the BERT model, edit `.env`:

```env
SOCKETIO_ASYNC_MODE=threading
LOAD_EMOTION_MODEL_ON_STARTUP=false
ENABLE_DEMO_SEED=true
DEMO_ADMIN_PASSWORD=admin12345
DEMO_USER_PASSWORD=user12345
```

Start the app:

```powershell
python app.py
```

Open `http://127.0.0.1:5000`.

## Maintenance CLI

Use the Flask CLI for repeatable setup and diagnostics:

```powershell
$env:FLASK_APP="wsgi:app"
flask smartcs init-db
flask smartcs seed-demo
flask smartcs check-models
```

| Command | Purpose |
| --- | --- |
| `flask smartcs init-db` | Create database tables and indexes without demo data. |
| `flask smartcs seed-demo` | Create configured demo accounts, sample orders, knowledge-base entries, and quick replies. |
| `flask smartcs check-models` | Report optional emotion-model configuration without loading large model weights. |

### Option B: Docker Compose

```bash
docker compose up --build
```

Open `http://127.0.0.1:5000`.

Docker Compose includes safe demo defaults. Create `.env` from `.env.example` only when you want to override ports, credentials, model loading, or LLM provider settings.

## Demo Accounts

Demo accounts are created only when `ENABLE_DEMO_SEED=true` and both demo passwords are set.

| Role | Environment variables |
| --- | --- |
| Admin | `DEMO_ADMIN_USERNAME`, `DEMO_ADMIN_PASSWORD` |
| Customer | `DEMO_USER_USERNAME`, `DEMO_USER_PASSWORD` |

The default `.env.example` uses placeholder passwords. Replace them before running a public or shared instance.

## LLM and Model Configuration

SmartCS supports OpenAI-compatible chat APIs:

```env
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

If `LLM_API_KEY` is empty, the app returns deterministic fallback replies so the UI and workflow remain testable.

The default emotion model directory is:

```text
models/my_finetuned_bert/
```

For development, CI, and quick demos, set:

```env
LOAD_EMOTION_MODEL_ON_STARTUP=false
```

Large model binaries should not be committed to Git. Publish model artifacts through a release asset or a model registry such as Hugging Face, then document the download command.

## Architecture

The project is in a transitional architecture:

```text
smartcs/
  __init__.py          # create_app(config_name=None)
  config.py            # development/testing/production config
  extensions.py        # db/login/csrf/limiter/socketio extension instances
  legacy_app.py        # compatibility layer; current routes live here
  models.py            # model export entrypoint
  services/            # migrated service modules
  repositories/        # repository exports
  routes/              # target location for Blueprint migration
  socket_handlers.py   # Socket.IO handler export entrypoint
```

The next major maintainability milestone is splitting `smartcs/legacy_app.py` into Blueprints and focused services. See [OPEN_SOURCE_UPGRADE_PLAN.md](OPEN_SOURCE_UPGRADE_PLAN.md).

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=smartcs --cov=services --cov=repositories --cov=utils
```

The current test suite focuses on:

- `create_app("testing")` configuration
- Admin API authorization boundaries
- Socket.IO room authorization
- Intent classification
- LLM fallback behavior
- Crisis intervention service behavior

## Security Notes

- Session cookies use `HttpOnly` and `SameSite=Lax`.
- Production requires `SECRET_KEY`.
- Socket.IO room joins validate session ownership.
- CORS defaults to local development origins and should be explicit in production.
- Responses include conservative browser security headers.
- JSON write endpoints currently use login-state protection while CSRF is disabled globally for compatibility. Enabling per-endpoint CSRF tokens is a planned hardening task.

Please report vulnerabilities through [SECURITY.md](SECURITY.md).

## Roadmap

- [ ] Replace placeholder screenshots with real assets.
- [ ] Add a public demo video/GIF.
- [ ] Split `legacy_app.py` into Flask Blueprints.
- [x] Add CLI commands for database init, demo seed, and model checks.
- [ ] Add provider adapters for DeepSeek, OpenAI, and local OpenAI-compatible endpoints.
- [ ] Add model artifact download docs.
- [ ] Raise coverage on services, routes, and Socket.IO flows.
- [ ] Publish versioned releases and changelog entries.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), then look for issues labeled `good first issue`, `help wanted`, or `documentation`.

## License

MIT. See [LICENSE](LICENSE).


