---
name: fastapi-backend-routes
description: FastAPI backend routing conventions, Pydantic data schemas, SQLite WAL concurrency, and market data freshness checks.
---

# FastAPI Backend & Data Pipeline Protocol

This skill dictates FastAPI endpoint implementation, data cache management, and SQLite database safety in `src/qx/interfaces/web.py`.

## 1. Schema Validation & Types
- Define request payloads using Pydantic `BaseModel`.
- Enforce strict CORS middleware for local ports `5173`, `5174`, `8510`.

## 2. Publication State Control
- API responses must include explicit `publication_state` (`VERIFIED`, `RESEARCH_ONLY`, `SIMULATED`, `BLOCKED`).
- Return `503 Service Unavailable` or `publication_state: BLOCKED` when required market data is stale or missing.

## 3. SQLite Concurrency
- Configure SQLite connections with:
  - `PRAGMA journal_mode=WAL;`
  - `PRAGMA busy_timeout=10000;`
  - `PRAGMA synchronous=NORMAL;`
