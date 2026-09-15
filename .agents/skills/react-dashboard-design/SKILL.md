---
name: react-dashboard-design
description: React workspace component patterns, visual design tokens, ErrorBoundary isolation, Bento-grid layout, and UI QA Agent visual audit protocols.
---

# React Dashboard Design Protocol

This skill governs UI layout standards, visual aesthetics, error handling, Bento-Grid architecture, and UI QA subagent visual auditing in the QX React frontend (`web/src`).

## 1. Visual Design System & Tokens
- **Background Palette**: Anti-fatigue dark slate `#0b0f17` (Canvas) & `#121824` (Card Surface).
- **Border Palette**: Glassmorphic dark slate `1px solid #1e293b`.
- **Signal Accents**: Muted Cyan `#38bdf8`, Emerald `#34d399`, Amber `#fbbf24`, Rose `#f87171`.
- **Typography**: Clean sans-serif with monospace data numeric rendering (`font-mono`).

## 2. Bento-Grid Layout Architecture
- **Top Telemetry Header (`h-14`)**: 56px fixed header bar displaying macro quotes (SPX, VIX, CVD, Portfolio Delta, WebSocket status).
- **Left Navigation Sidebar (`w-16`)**: 64px compact icon navigation sidebar.
- **12-Column Responsive Bento Grid**: Main stage divided into modular bento cells (`col-span-8` main stage, `col-span-4` secondary panel, `col-span-12` multi-row table).

## 3. Defensive Formatting & Error Isolation
- Format numeric values using defensive helpers: `(Number(val) || 0).toFixed(decimals)`.
- Wrap all workspace panels in `<ErrorBoundary title="...">` to prevent global unhandled UI crashes.

## 4. UI QA Agent Visual Audit Protocol
- **Browser Subagent Inspections**: Subagents must launch `browser_subagent` to test the live app at `http://127.0.0.1:5174/`.
- **Multi-Viewport Audit**: Verify rendering across Desktop (1920x945), Laptop (1440x900), Tablet (768x1024), and Mobile (390x844).
- **Visual Evidence Recording**: Save interactive WebP session videos (`application_run_demo.webp`) and PNG screenshots into the artifact directory.
- **Console Log Hygiene**: Verify 0 Uncaught TypeErrors and 0 WebSocket socket crash warnings.
