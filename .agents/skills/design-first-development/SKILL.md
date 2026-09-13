---
name: design-first-development
description: >-
  Standard protocol for software development on the QX Platform:
  Require skill setup, architectural design preparation, user review,
  and automated regression verification before building.
---

# Design-First Development Protocol

This skill enforces a disciplined 4-stage engineering process for all task execution.

## Stage 1: Skill Setup & Workflow Check
- Before modifying or adding code, identify what domain skills are involved (e.g. market indicators, options scanner, position advisor, UI design system).
- Verify instructions in `.agents/skills/` or create new skill definitions if a new domain pattern is established.

## Stage 2: Architecture & Design Specification
- Outline a structured `implementation_plan.md`:
  - Technical goal & requirements
  - Component impact & file demarcations
  - Data schema & API contracts
  - Risk drivers & edge cases

## Stage 3: User Review & Alignment
- Present the implementation plan to the user.
- Highlight breaking changes, architectural trade-offs, and open questions.
- Wait for feedback or explicit approval before editing source files.

## Stage 4: System Implementation & Pre-Flight Verification
- Execute code changes cleanly following system design rules.
- Run automated pre-flight & regression suites:
  - `pytest tests/regression/`
  - `python -m qx.tools.run_preflight_checks`
- Embed visual evidence / logs in `walkthrough.md`.
