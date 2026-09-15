# QX Platform — Institutional Quantitative Analytics & Options Risk Engine

The **QX Platform** is an institutional-grade quantitative trading workspace, options risk engine, and market structure analytics platform. Built with a **FastAPI / Python 3.12 backend**, a **React 19 / Vite 6 frontend**, and **Antigravity IDE custom AI agent orchestration skills**.

---

## 🌟 Key Platform Features

- **Sector Rotation & Relative Strength Engine**: Real-time 5d/20d/60d RS alignment, ETF quadrant tracking, and benchmark outperformance rankings.
- **Institutional Options Scanner & Risk Sizer**: Dynamic position sizing using Black-Scholes Greeks, IV/RV edge profiles, 100x contract multipliers, and standard contract symbol formatting.
- **SPX Command Dashboard & GEX Profiler**: SPX futures tracking, 15m Opening Range Breakouts (ORB), VWAP upper/lower bounds, and gamma flip level detection.
- **Read-Only Brokerage Interface**: Fail-closed security architecture (`ReadOnlyBrokerPortfolioProvider`) ensuring non-destructive portfolio management.
- **Zero-Crash Defensive Frontend**: Fully defensive numeric template formatting (`(Number(val) || 0).toFixed(...)`) and React ErrorBoundary isolation across workspace cards.
- **Antigravity IDE Customization System**: Integrated rules (`code_quality.md`), domain skills (`ai-agent-orchestration`, `options-pricing-and-greeks`, `react-dashboard-design`, `fastapi-backend-routes`), and automated git pre-commit hooks (`.git/hooks/pre-commit`).

---

## 🏗️ Architecture & Documentation Blueprint

- 📐 **[Future Architecture Blueprint](QX_Platform_Future_Architecture_AI_Agent_FINAL.md)**: Executive architectural specification and multi-stage agent design.
- 📋 **[Implementation Plan](QX_Implementation_Plan.md)**: System design and component demarcations.
- 📜 **[System Walkthrough](QX_Walkthrough.md)**: End-to-end verification and visual evidence audit.
- 🤖 **[Antigravity Custom Agent Skills](.agents/skills/)**: Custom skill definitions for Quantitative Analytics, Options Risk, React UI Design, and FastAPI routes.

---

## 🚀 Quickstart & Operations

### 1. Diagnostic Preflight Verification
Verify that all 13 core backend APIs, market data providers, and frontend servers are healthy:
```bash
# Windows / Virtualenv Python
.venv\Scripts\python.exe -m qx.tools.run_preflight_checks
```

### 2. Running Unit & Integration Tests
```bash
# Python Backend Test Suite (1,700+ tests)
.venv\Scripts\python.exe -m pytest tests/unit/

# Frontend Test Suite (18 tests)
cd web && npm test
```

### 3. Launching Local Development Servers
```bash
# Backend FastAPI Server (Port 8510)
.venv\Scripts\python.exe -m uvicorn qx.interfaces.web:create_app --factory --host 127.0.0.1 --port 8510

# Frontend React Dashboard (Port 5174)
cd web && npm run dev
```

---

## 🔒 Security & Safety Defaults

- **Publication State**: Default state `SIMULATED` or `VERIFIED`; automatically falls closed to `BLOCKED` if real-time feeds are unreachable.
- **Broker Interface**: Strict read-only mode (`is_read_only: true`).
- **Pre-Commit Enforcement**: The repository uses `.git/hooks/pre-commit` to prevent committing code that fails diagnostic preflight checks or unit tests.
