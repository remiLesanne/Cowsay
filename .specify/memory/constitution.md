<!--
Sync Impact Report
- Version change: (none) → 1.0.0 (initial ratification)
- Modified principles: n/a (first version)
- Added sections: Core Principles (5), Technology Constraints, Development Workflow, Governance
- Removed sections: none
- Templates requiring updates: plan-template.md, spec-template.md, tasks-template.md — not yet
  reviewed against this constitution; flag for check next time /speckit-plan runs.
- Follow-up TODOs: TODO(RATIFICATION_DATE) is set to the date this constitution was authored
  (2026-09-26), since no earlier written agreement exists.
-->

# Cowsay (EU AI Act Compliance Checker) Constitution

## Core Principles

### I. Drive the Real Tool, Never Reimplement It
When correctness depends on matching an external authority exactly (e.g. the official EU AI
Act Compliance Checker), the system MUST interact with the real tool (browser automation,
API calls) rather than reimplementing its logic locally. A reimplementation can drift from the
original and silently produce wrong answers with no way to detect it; driving the real tool
makes correctness a property of the integration, not of guesswork.

### II. No Silent Guessing — Escalate Uncertainty to a Human
When the AI agent cannot determine an answer from the available code/context with reasonable
confidence, it MUST say so explicitly (e.g. `needs_human_input`) rather than inventing a
plausible-sounding answer. This is a direct product requirement (the compliance checker must
ask a human, or ask for a missing document, when information is missing) and a general
principle for any agentic feature in this codebase.

### III. Spec-Driven Development When Using an AI Coding Harness
This project is built with an AI coding harness (Claude Code). Per the course rubric, that
requires using a spec-driven/agentic development framework (Spec Kit) instead of ad-hoc
"vibe coding": non-trivial features go through `/speckit-specify` → `/speckit-plan` →
`/speckit-tasks` → `/speckit-implement` (or an equivalent documented spec/plan/tasks trail),
not straight-to-code requests, so the team can show planning, specs, and acceptance criteria.

### IV. Production-Shaped, Not a POC
Architecture decisions must consider security, cost, and integration with existing
infrastructure as if this were a real product, not a one-off demo (explicit grading
criterion). Concretely: secrets never committed (env vars / secret manager only), upload
limits and timeouts sized deliberately (not left at arbitrary defaults), and cloud deploys
go through the CI/CD pipeline, not manual pushes to production.

### V. Documentation Stays Current and Token-Lean
`README.md` MUST reflect the actual current state of the system (what's implemented, why,
what's left) after every feature that changes that state — written densely enough that a
fresh AI session or teammate can load full project context cheaply, without re-deriving it
from source. Stale or verbose documentation is treated as a defect, not a nice-to-have.

## Technology Constraints

- Backend: FastAPI (Python), deployed as a Docker image.
- Frontend: Next.js.
- Code-to-text preprocessing: Repomix (Node.js CLI, invoked as a subprocess).
- Compliance agent: Playwright (headless Chromium) drives the official checker page;
  the LLM (Z.AI GLM models, OpenAI-compatible API) answers each question from the
  Repomix-derived code context.
- Cloud target: AWS ECS on Fargate (cluster `default`), Canary deploy strategy, images in
  Amazon ECR, deployed via GitHub Actions (`.github/workflows/deploy.yml`).
- Planned, not yet built: managed PostgreSQL (Supabase or Neon) for user accounts/auth.
- Secrets (API keys, DB URLs) are supplied via environment variables — `.env` locally
  (git-ignored), ECS task definition environment/secrets in production — never hardcoded.

## Development Workflow

- One git branch per feature or clearly separable major chunk of work; push to origin as
  soon as that piece works, so any regression is easy to roll back from. Do not accumulate
  multiple unrelated features on a single branch.
- Non-trivial features follow the Spec Kit flow (Principle III) with artifacts committed
  under `specs/`; trivial fixes (typos, config tweaks, obvious bugs) may skip straight to a
  commit but should still land on their own branch.
- Commit messages and PR descriptions state the "why", not just the "what".

## Governance

This constitution supersedes ad-hoc practice for this repository. Amendments are made via
`/speckit-constitution`, must state a reason, and bump the version per semantic versioning
(MAJOR: principle removed/redefined incompatibly; MINOR: principle or section added;
PATCH: wording/clarity fixes). Any PR or review that conflicts with a principle here must
either be changed to comply or the constitution amended first — silent exceptions are not
permitted.

**Version**: 1.0.0 | **Ratified**: 2026-09-26 | **Last Amended**: 2026-09-26
