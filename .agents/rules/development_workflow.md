# Development Workflow Rule: Skill & Design First

## Core Principle: No Rushing into Build

Never jump straight into writing code or modifying implementations without first completing the prerequisite skill setup, design preparation, and user review.

---

## Mandatory Step-by-Step Workflow

1. **Step 1: Skill Assessment & Setup**
   - For any non-trivial feature, task, or workflow, check if a dedicated **Skill** (`.agents/skills/<skill_name>/SKILL.md`) exists.
   - If missing or incomplete, define and record the skill instructions first.

2. **Step 2: Architecture & Design Plan**
   - Prepare a clear design specification / implementation plan (`implementation_plan.md`).
   - Document technical requirements, component changes, data schemas, risk considerations, and open questions.

3. **Step 3: User Alignment & Feedback**
   - Present the implementation plan to the user for review.
   - Wait for explicit user feedback or approval before making source code edits.

4. **Step 4: Build, Test & Verify**
   - Execute the approved plan systematically.
   - Run automated pre-flight checks and regression tests (`python -m qx.tools.run_preflight_checks` & `pytest tests/`) to verify 100% compliance before declaring ready for viewing.
