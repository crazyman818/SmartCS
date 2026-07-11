# SmartCS Demo Assets

This directory is reserved for release-ready screenshots, diagrams, and short demos used by the public README.

## Required first-release assets

| File | Purpose | Capture guidance |
| --- | --- | --- |
| `chat.png` | Customer-facing AI chat workflow. | Show a realistic customer message, an AI reply, and visible order/refund context. |
| `admin-chat.png` | Operator console and human intervention flow. | Show conversation monitoring, room selection, and an admin reply. |
| `dashboard.png` | Analytics dashboard with seeded demo data. | Include message, satisfaction, emotion, and refund panels where available. |
| `demo.gif` | 20-40 second product walkthrough. | Cover customer chat, AI response, escalation, and admin intervention. |
| `architecture.png` | System architecture diagram. | Show browser clients, Flask, Socket.IO, services, SQLite, LLM provider, and optional emotion model. |

## Quality bar

- Use seeded demo data instead of personal or production customer data.
- Capture at 1440px desktop width when possible, then crop only empty browser chrome.
- Keep UI text readable in the GitHub README preview.
- Prefer PNG for screenshots and diagrams; keep GIFs short enough to load quickly.
- Update the README screenshot table whenever filenames change.