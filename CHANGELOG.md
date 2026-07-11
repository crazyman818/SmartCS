# Changelog

All notable changes to SmartCS will be documented in this file.

The project follows semantic versioning once public releases begin.

## Unreleased

### Added

- Open-source upgrade roadmap.
- MIT license.
- Contributing guide.
- Security policy.
- GitHub issue templates and pull request template.
- GitHub Actions test workflow.
- Docker and Docker Compose quick-start files with safe demo defaults and no required local `.env` file.
- Flask CLI commands for database initialization, demo seeding, and model checks.
- Shared bootstrap helpers for local, Docker, and CLI startup initialization.
- Migrated auth route implementations into `smartcs.routes.auth` with compatibility tests.
- Migrated customer chat route implementations into `smartcs.routes.chat` with permission and message-flow tests.
- Migrated refund workflow and refund analytics route implementations into `smartcs.routes.refunds` with ownership, permission, approval, and alert-metric tests.
- Migrated dashboard page and core dashboard summary/trend route implementations into `smartcs.routes.dashboard` with permission and metric tests.
- Migrated knowledge-base admin route implementations into `smartcs.routes.knowledge` with ownership, permission, CRUD, validation, and rebuild tests.
- Documented expected README screenshot, GIF, and architecture assets under `docs/assets/`.
- Disabled request rate limiting under testing configuration to keep CI permission tests deterministic.

### Changed

- Reworked README into a GitHub-facing project landing page with clearer positioning, setup, testing, security, and roadmap sections.

