---
name: react-dashboard-design
description: React workspace component patterns, visual design tokens, ErrorBoundary isolation, Bento-grid layout, and UI QA Agent visual audit protocols.
---

# React Dashboard Design Protocol

This skill governs UI layout standards, visual aesthetics, error handling, Bento-Grid architecture, and UI QA subagent visual auditing in the QX React frontend (`web/src`).

## 1. Visual Design System & Tokens (Eye Comfort & Anti-Fatigue)
- **Background Palette**: Anti-fatigue deep dark canvas `#080c14` & `#0f1522` (Card Surface).
- **Border Palette**: Low-glare glassmorphic dark slate `1px solid #1c2638`.
- **Primary Text**: Soft low-strain off-white `#cbd5e1` (never stark glare `#ffffff`).
- **Secondary Text**: Soft cool slate `#8a99ad` & `#94a3b8`.
- **Signal Accents**: Muted Cyan `#38bdf8`, Emerald `#2ebd85`, Soft Amber `#e5c07b`, Softer Rose `#e06c75`.
- **Typography**: Clean sans-serif with monospace data numeric rendering (`font-mono`).

## 2. Bento-Grid Layout Architecture
- **Top Telemetry Header (`h-14`)**: 56px fixed header bar displaying macro quotes (SPX, VIX, CVD, Portfolio Delta, WebSocket status).
- **Left Navigation Sidebar (`w-16`)**: 64px compact icon navigation sidebar.
- **12-Column Responsive Bento Grid**: Main stage divided into modular bento cells (`col-span-8` main stage, `col-span-4` secondary panel, `col-span-12` multi-row table).

## 3. Defensive Formatting & Error Isolation
- Format numeric values using defensive helpers: `(Number(val) || 0).toFixed(decimals)`.
- Wrap all workspace panels in `<ErrorBoundary title="...">` to prevent global unhandled UI crashes.

## 4. UI QA Agent Visual Audit & Eye Comfort Protocol
- **Browser Subagent Inspections**: Subagents must launch `browser_subagent` to test the live app at `http://127.0.0.1:5174/`.
- **Eye Comfort Verification**: Inspect contrast levels and colors to ensure low glare, anti-fatigue dark-mode aesthetic (matching Antigravity IDE comfort standards).
- **Multi-Viewport Audit**: Verify rendering across Desktop (1920x945), Laptop (1440x900), Tablet (768x1024), and Mobile (390x844).
- **Visual Evidence Recording**: Save interactive WebP session videos (`application_run_demo.webp`) and PNG screenshots into the artifact directory.
- **Console Log Hygiene**: Verify 0 Uncaught TypeErrors and 0 WebSocket socket crash warnings.
