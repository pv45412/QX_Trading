# Today Specification

## Purpose

Today answers one question: **What matters now?** It is an attention and routing page,
not another scanner and not a duplicate Trade Workspace.

## Section Order

### 1. Market Pulse

Compact session context:

- major index movement and volatility context from verified sources
- session status and evaluation timestamp
- concise structure/regime summary when canonical data supports it
- a clear unavailable/partial state when market context is incomplete

The current static or placeholder header metrics must not be elevated as verified data.

### 2. Market Drivers

- primary driver, strength, persistence, and coverage from the future backend contract
- up to a small number of secondary drivers
- confirming/conflicting counts
- link to expanded evidence in Trade or Research

Until a deterministic source exists, show unavailable rather than infer from news or
market color.

### 3. Active QX Opportunities

A short, prioritized subset of Opportunities:

- symbols in meaningful canonical states
- lifecycle state, direction, trigger/invalidation, risk state, and freshness
- direct link to Trade Workspace

Do not reproduce full scanner filters or long indicator tables.

### 4. Positions Requiring Attention

Read-only broker portfolio alerts:

- risk constraint or concentration issue
- stale/partial account evidence
- invalidation/monitoring condition where linked to a canonical setup
- direct link to Portfolio or Trade Workspace

This section is unavailable when no canonical account snapshot exists. ETF constituent
holdings do not populate it.

### 5. Important Events / Data Health

Show only material items:

- imminent market events when a supported source exists
- provider authentication/freshness failure affecting decisions
- blocked canonical dependencies

Healthy operational detail stays in System. Today must not become a permanent status
dashboard.

## Actions

- choose `DAY`, `SWING`, or `INVEST` context
- open an opportunity in Trade Workspace
- open a position in Portfolio
- inspect a material health issue in System
- refresh read-only data

No credential editing, deep research control, or execution action appears here.

## Use of Current Components

- Reuse selected presentation patterns from `QXDayTraderTerminal`, not its competing
  signal-state model.
- Reuse concise SPX/futures/session context from `SPXFuturesWorkspace` where sourced.
- Reuse mover/ranking summaries as discovery context, not canonical opportunities.
- Treat `QXDailyNewsPrompt` as a research/context source only; static prompts do not
  become market drivers.
- Use compact canonical lifecycle summaries linked to the full `QXLifecyclePanel` in
  Trade Workspace.

## Content Limits

- Maximum one primary decision per section.
- Prefer five active opportunities over an unbounded scanner table.
- Prefer exception-only portfolio and health items.
- Keep WHY/evidence collapsed and linked to the owning destination.
- Never duplicate the entire Markets composite page.

## Empty-State Examples

- “No canonical opportunities require attention.”
- “Broker portfolio unavailable; connect or verify the read-only account provider in
  System.”
- “Market driver unavailable; other canonical evidence remains visible.”
- “All monitored data sources are within their reported freshness windows.”
