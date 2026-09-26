# Research: Human-in-the-Loop Answers

## Decision: In-memory session cache, not a database

**Rationale**: The project has no database yet (see README.md "Not done yet"), and
adding one just to cache a `ProjectIndex` for up to ~30 minutes would be disproportionate
infrastructure for what this needs. A module-level dict keyed by a UUID, with an
`expires_at` checked on access, is the smallest thing that satisfies FR-002/FR-007.

**Alternatives considered**: Redis (real production choice for multi-instance
deployments, but this project runs a single ECS task — no need yet); re-uploading the
file on every resume round and rebuilding the index each time (rejected — defeats
SC-001/FR-002, and directly reintroduces the cost spec 002's research.md already
measured as expensive for large projects).

**Trade-off accepted**: session state is lost on process restart/redeploy. Acceptable for
a school-project single-instance deployment; would need a shared store to survive that,
tracked as a follow-up limitation (same treatment as spec 002's 500MB gap).

## Decision: Validate multiple-choice answers server-side before launching Playwright

**Rationale**: FR-003/SC-002 require rejecting an invalid answer without wasting a
30-90s browser run. The question's real options are already known from the round-1
result (`needs_human_input[].options`), so validation is a simple set-membership check
against those cached options before touching Playwright at all.

**Alternatives considered**: letting the checker site itself reject the value (can't —
we drive it via direct DOM clicks, and clicking a non-existent option is either a no-op
or a crash, neither of which is a useful error message); trusting the frontend's own
validation alone (rejected — an API caller bypassing the frontend, e.g. curl, must get
the same protection per FR-003, which doesn't mention "UI-only").

## Decision: Frontend renders options as real choice controls, not free text

**Rationale**: FR-006/SC-003 — the simplest way to guarantee an invalid answer can never
be *typed* for a multiple-choice question is to not offer a text box for it: render radio
buttons (single-select) or checkboxes (multi-select) sourced directly from
`needs_human_input[].options`, matching the field's `type`. Free-text questions (no
`options` in the payload) keep a text input, since there's nothing to validate against.

**Alternatives considered**: a free-text box with client-side fuzzy matching against
options (rejected — more code, still needs the server-side check anyway for API callers,
and doesn't actually improve on just showing the real choices).

## Decision: Resume re-runs the whole Playwright session, not a resumed browser page

**Rationale**: Keeping a live headless Chromium page open across HTTP requests (true
mid-session resumption) would need per-session browser process lifecycle management,
health checks, and cleanup on client abandonment — real complexity for a benefit
(skipping a 30-90s browser run) that's smaller than the benefit of NOT re-running Repomix
+ embeddings on a resume (already solved by caching `ProjectIndex`). Re-running the
browser session but skipping the LLM call for already-answered fields is a much smaller
change with most of the win.

**Alternatives considered**: keeping the browser/page alive in the session cache
alongside the index — rejected for this iteration; flagged as a future optimization if
the 30-90s-per-round-trip cost turns out to matter in practice once used for real.
