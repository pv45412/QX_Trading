---
name: react-dashboard-design
description: React workspace component patterns, visual design tokens, ErrorBoundary isolation, and URL router state preservation.
---

# React Dashboard Design Protocol

This skill governs UI layout standards, visual aesthetics, error handling, and navigation context in the QX React frontend (`web/src`).

## 1. Visual Design System & Tokens
- **Background**: Dark slate `#0b0f17` & `#0f172a`.
- **Borders**: Glassmorphic `1px solid rgba(255, 255, 255, 0.08)`.
- **Accents**: Cyan `#00f2fe`, Emerald `#10b981`, Amber `#f59e0b`, Rose `#ef4444`.
- **Typography**: Clean sans-serif with strong hierarchy (Inter / Outfit style).

## 2. Defensive Formatting Rules
- Format numeric values using defensive helpers: `(Number(val) || 0).toFixed(decimals)`.
- Wrap all workspace panels in `<ErrorBoundary title="...">` to prevent global unhandled UI crashes.

## 3. URL Router & Context State
- Preserve URL search context (`symbol`, `etf`, `page`) when switching tabs or clicking quick-jump buttons.
- Dispatch `workspacecontextchange` events on `window.history.pushState` updates.
