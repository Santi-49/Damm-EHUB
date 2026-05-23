# Documentation

## Architecture
- [System Overview](architecture/overview.md) — services, request flow, component map
- [LineWise (Arch D)](architecture/linewise.md) — graph-based optimiser + SKU-to-SKU edge costs + simulator
- [ADR 001 — Module Contract](architecture/adr/001-module-contract.md) — why the module boundary exists

## LineWise (challenge)
- [Functionality map](functionalities/overview.md) — five workspaces, owners, contracts
- [Data products catalogue](data/overview.md) — every clean CSV, schema, lineage
- [Data cleaning rules](data/cleaning_rules.md) — derivations, outliers, discarded files
- [Datos](linewise/datos.md) — raw Excel inventory, joins, clean schema (original analysis)
- [Reto](linewise/reto.md) — problem statement, objective function, post-mortem methodology
- [Implementación](linewise/implementacion.md) — Arch D deep dive vs alternatives
- [Resumen](linewise/resumen.md) — visual overview, Gantt, sync points
- [Cobertura brief](linewise/cobertura_brief.md) — brief-by-brief coverage check

## Backend
- [Backend Overview](backend/overview.md) — stack, folder structure, how to run
- [Authentication](backend/auth.md) — JWT flow, Redis whitelist, token lifecycle
- [RBAC](backend/rbac.md) — OPA policies, roles, permissions, how to extend
- [API Reference](backend/api-reference.md) — all endpoints with request/response shapes
- [Database](backend/database.md) — schema, models, Alembic migrations

## Challenge
- [Challenge](challenge/CHALLENGE.md) — problem statement, rules, data, judging criteria
- [Vision](challenge/VISION.md) — solution concept, key features, demo script
- [Constraints](challenge/CONSTRAINTS.md) — scope, team, timeline, design language
- [Research](challenge/RESEARCH.md) — company background, market context, recommendations

## Hackathon Workflow
- [Getting Started](getting-started.md) — setup, repo orientation, and contracts explained for humans
- [Module Contracts](contracts.md) — how to wire challenge-specific logic into the backend
- [Onboarding](onboarding.md) — Day-0 setup for new teammates
- [MCP Servers](mcp-servers.md) — AI agent tooling: Postgres, Playwright, Docker, Fetch, MarkItDown
