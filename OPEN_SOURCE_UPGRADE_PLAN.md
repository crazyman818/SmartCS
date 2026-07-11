# SmartCS Open-Source Upgrade Plan

This plan turns SmartCS from a working graduation-project codebase into a repository that feels credible, easy to try, and worth starring.

## North Star

SmartCS should be positioned as:

> An open-source AI customer service copilot for e-commerce teams, with emotion-aware escalation, RAG answers, human handoff, refund workflows, and an operator dashboard.

The project should optimize for three visitor decisions:

1. "I understand what this does in 30 seconds."
2. "I can run it in 5 minutes."
3. "The codebase looks maintainable enough to trust or contribute to."

## Current Readiness Snapshot

Strengths:

- End-to-end product surface already exists: chat, admin console, refunds, dashboard, RAG, LLM fallback, emotion detection.
- Flask app factory and test configuration exist.
- Test suite covers several critical security and service boundaries.
- UI has an explicit design standard in `DESIGN.md`.

Main gaps:

- `smartcs/legacy_app.py` is still too large and mixes app setup, models, routes, services, WebSocket handlers, and seed logic.
- The repository was missing common community files and CI.
- No containerized quick-start path existed.
- README needed a stronger GitHub landing-page structure with screenshots, positioning, roadmap, and contribution path.
- Model artifact distribution and demo setup need clearer long-term handling.

## Phase 1: GitHub First Impression

Target: a visitor can understand, trust, and try the repository quickly.

- Rewrite README with a crisp product pitch, feature list, quick start, screenshots section, architecture note, tests, security, and roadmap.
- Add `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, issue templates, PR template, and GitHub Actions test workflow.
- Add `Dockerfile`, `docker-compose.yml`, and `.dockerignore`.
- Add real screenshots/GIF under `docs/assets/` before publishing.
- Keep non-repository-specific badges until the public repository path is known; switch the test badge to the real GitHub Actions workflow URL after publishing.

Exit criteria:

- Fresh clone can run tests.
- Fresh clone can run the app locally or with Docker Compose; Docker Compose does not require a pre-existing `.env` file.
- GitHub repository community profile is mostly complete.

## Phase 2: One-Command Demo

Target: reduce the time-to-demo below five minutes.

- Add CLI commands (implemented):
  - `flask smartcs init-db`
  - `flask smartcs seed-demo`
  - `flask smartcs check-models`
- Make demo mode explicit and safe:
  - Demo seed is disabled by default in production.
  - Demo credentials must be provided through environment variables.
  - The app runs without LLM and without BERT model files.
- Add sample knowledge-base data and sample conversations that make the dashboard look alive.
- Add a demo script or GIF capture recipe.

Exit criteria:

- A new contributor can create demo accounts and sample data without reading implementation internals.
- The README demo path matches actual commands.

## Phase 3: Architecture Refactor

Target: make the codebase readable enough for external contributors.

Split `smartcs/legacy_app.py` into focused modules:

```text
smartcs/
  routes/
    auth.py
    chat.py
    admin.py
    refunds.py
    dashboard.py
    knowledge_base.py
  services/
    emotion_service.py
    llm_service.py
    rag_service.py
    crisis_service.py
    refund_service.py
    dashboard_service.py
  repositories/
    users.py
    chats.py
    refunds.py
    knowledge_base.py
  models/
    user.py
    chat.py
    order.py
    refund.py
    knowledge_base.py
  cli.py
  socket_handlers.py
```

Refactor rules:

- Keep public URLs and JSON response shapes stable during the migration.
- Move one domain at a time and add tests around each moved route/service.
- Auth route implementations have been moved into `smartcs.routes.auth` while preserving legacy endpoint names.
- Customer chat route implementations have been moved into `smartcs.routes.chat` while preserving legacy endpoint names.
- Refund workflow and refund analytics route implementations have been moved into `smartcs.routes.refunds` while preserving legacy endpoint names.
- Dashboard page and core dashboard summary/trend route implementations have been moved into `smartcs.routes.dashboard` while preserving legacy endpoint names.
- Knowledge-base admin route implementations have been moved into `smartcs.routes.knowledge` while preserving legacy endpoint names.
- Avoid changing UI behavior during backend modularization unless a test exposes a bug.
- Keep the fallback behavior for no LLM key and no BERT model.

Exit criteria:

- Shared startup/bootstrap logic is centralized outside entrypoints. (Implemented for local, Docker, and CLI startup.)
- `legacy_app.py` is removed or reduced to a thin compatibility shim.
- Auth route behavior can be understood in `smartcs.routes.auth` without reading unrelated domains.
- Customer chat route behavior can be understood in `smartcs.routes.chat`, with remaining intent/RAG/LLM dependencies still bridged through the legacy compatibility layer.
- Refund workflow and refund analytics behavior can be understood in `smartcs.routes.refunds`.
- Dashboard page, dashboard user-status data, emotion stats, and summary/trend APIs can be understood in `smartcs.routes.dashboard`.
- Knowledge-base admin page and CRUD/rebuild APIs can be understood in `smartcs.routes.knowledge`; remaining admin chat, quick-reply, profile, export, and user-management APIs still need later extraction.
- Each remaining route module can be understood without reading unrelated domains.
- Tests cover auth, chat, admin authorization, refund workflows, RAG fallback, LLM fallback, and Socket.IO room joins.

## Phase 4: Product Differentiation

Target: make SmartCS memorable rather than a generic chatbot demo.

Recommended headline feature:

> Emotion-aware AI support desk with human handoff.

Feature upgrades:

- Show intervention status clearly in the admin console.
- Add conversation timeline and escalation reasons.
- Add editable knowledge-base entries with retrieval preview.
- Add provider adapters for DeepSeek, OpenAI, and local OpenAI-compatible endpoints.
- Add import/export for knowledge-base Q&A.
- Add a small evaluation set for customer-support replies.
- Add role-based audit logs for sensitive admin actions.

Exit criteria:

- The README can show a compelling end-to-end flow: customer complaint -> emotion detection -> RAG answer -> escalation -> admin intervention -> dashboard insight.

## Phase 5: Maintenance System

Target: keep the repository active and contributor-friendly.

- Use semantic versioning once public releases begin.
- Maintain `CHANGELOG.md` for every release.
- Keep a GitHub Project board with `Now`, `Next`, and `Later`.
- Label issues with `good first issue`, `help wanted`, `bug`, `security`, `docs`, and `architecture`.
- Require CI checks before merging.
- Add coverage reporting after the core refactor stabilizes.
- Review dependencies monthly.
- Publish a short release note for every meaningful improvement.

## Suggested Release Milestones

### v0.1.0: Open-source baseline

- README, license, contributing docs, security policy, CI, Docker Compose.
- Verified local test run.
- Placeholder screenshot section documented.

### v0.2.0: Demo-ready product

- CLI setup commands for database init, demo seed, and model checks.
- Seeded demo data.
- Real screenshots and GIF.
- Model artifact documentation.

### v0.3.0: Maintainable architecture

- Major route/service split.
- Expanded tests.
- Reduced `legacy_app.py`.

### v0.4.0: Strong product story

- Improved intervention workflow.
- Knowledge-base retrieval preview.
- LLM provider adapters.
- Admin audit trail.

## Promotion Checklist

Before promoting the project publicly:

- [ ] Switch the generic test badge to the real GitHub Actions badge after the repository path is public.
- [ ] Add screenshots and a demo GIF.
- [ ] Confirm Docker Compose starts from a clean clone.
- [ ] Confirm README quick-start commands work on Windows and Linux/macOS.
- [ ] Add repository topics: `flask`, `ai`, `customer-service`, `rag`, `socketio`, `llm`, `ecommerce`, `chatbot`.
- [ ] Create 3-5 beginner-friendly issues.
- [ ] Publish a first release with notes and assets.
- [ ] Write a launch post explaining the emotion-aware handoff workflow.

