# Security Policy

## Supported Versions

SmartCS is currently pre-1.0. Security fixes should target the default branch until versioned releases begin.

## Reporting a Vulnerability

Please do not open a public issue for suspected vulnerabilities.

Report privately by contacting the repository maintainer or by using GitHub private vulnerability reporting if it is enabled for the repository.

Include:

- Affected version or commit.
- Steps to reproduce.
- Expected and actual behavior.
- Impact assessment.
- Any suggested fix, if known.

## Security Expectations

SmartCS handles authentication, chat records, customer-service workflows, and optional LLM calls. Contributors should be careful with:

- Session and authorization boundaries.
- Socket.IO room access.
- Admin-only APIs.
- Customer conversation export.
- Prompt injection and untrusted knowledge-base content.
- Secrets in `.env` files.
- Demo credentials and seeded data.

Never commit API keys, production secrets, private customer data, local databases, or large private model artifacts.
