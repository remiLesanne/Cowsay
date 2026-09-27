# Feature Specification: Concurrent Analyses (10+ simultaneous users)

**Feature Branch**: `feature/concurrent-analyses`

**Created**: 2026-09-27

**Status**: Implemented (2026-09-27) — all success criteria live-verified except the
frontend's visual rendering (no browser available; checked by lint/tsc/build only).
Results recorded in `tasks.md`.

**Input**: User description: "Let 10+ users run compliance checks at the same time. Today at
most MAX_CONCURRENT_CHECKS (2) run per process and extra requests get an immediate 503; the
whole check is one synchronous HTTP request bounded by the ALB's 300s idle timeout. Decided
with the user: (1) a queue is acceptable — every submission is accepted, runs when a slot
frees up, and the user sees they're queued with their position and an estimate, never an
error because others are using the platform; (2) stay on Mistral's free tier (measured: 100
requests/min, 100,000 tokens/min; ~4,800 tokens per question on a real project, so ~2-4
complete checks/min platform-wide) — the system must share that quota across concurrent
checks gracefully (no 429 storms) and spend fewer tokens (e.g. do not re-ask the LLM, on a
human-answer resume, questions it already answered — today every resume re-pays them all).
Also raise how many checks can progress in parallel on the current single ECS task (2 vCPU /
8 GB), e.g. by sharing one browser instead of launching Chromium per check. Resuming with
human answers must go through the same queue. Stays on a single backend instance (sessions
remain in memory — horizontal scaling out of scope). Frontend: submitting returns
immediately; the analysis page shows queued/running/done/failed and refreshes until done."

## Context

Measured before this feature (2026-09-27): the platform turns away every submission beyond
the 2nd simultaneous one with a "server busy" error, and a single check must finish within
the load balancer's 5-minute request limit or the user gets a gateway error. The language
model provider's free quota (100 requests and 100,000 tokens per minute, shared by the whole
platform) caps throughput at roughly 2–4 complete checks per minute whatever the server
size — so serving 10+ simultaneous users means *queuing fairly and visibly*, not running
everything at once.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit and follow an analysis without waiting on the request (Priority: P1)

A user submits their code and/or PDF. The platform immediately confirms the analysis is
accepted and takes them to its page, which shows where it stands — waiting, in progress,
done, or failed — and updates by itself until the result is there. The user can close the
page and find the analysis later in their history, still progressing or finished.

**Why this priority**: Everything else depends on it. As long as a check has to fit inside
one request, any wait (queue, slow provider, big project) turns into a gateway error.

**Independent Test**: Submit one analysis; confirm the submission is acknowledged within
seconds, the analysis page shows "in progress" then the final result without any manual
reload, and that closing the tab mid-run and reopening it from history shows the finished
result.

**Acceptance Scenarios**:

1. **Given** a logged-in user with a valid file, **When** they submit, **Then** the
   submission is acknowledged within 5 seconds (excluding upload transfer time) and they
   land on the analysis page showing its current status.
2. **Given** an analysis in progress, **When** the user stays on its page, **Then** the page
   updates on its own and shows the full result (same content as today) once done.
3. **Given** an analysis in progress, **When** the user leaves and later reopens it from
   their history, **Then** they see its current status or its final result.
4. **Given** a check that takes longer than 5 minutes (e.g. a large project), **When** it
   runs, **Then** it completes and its result is shown, instead of ending in a timeout error.
5. **Given** an analysis that fails (checker site unreachable, provider down after
   retries), **When** the user looks at it, **Then** it is shown as failed with a
   plain-language reason and an invitation to resubmit.

---

### User Story 2 - Many users at once: wait your turn, never an error (Priority: P1)

Ten or more people (e.g. a whole class during a demo) submit analyses within the same
minute. Every submission is accepted. Those that can't start yet wait in a queue; each
waiting user sees their position and an estimated wait, both updating as the queue moves.
Everyone eventually gets their result; nobody is told the platform is busy.

**Why this priority**: This is the need the feature exists for.

**Independent Test**: Have 12 accounts submit an analysis within the same minute; confirm all
12 are accepted, queued users see a position and an estimate that decrease over time, and
all 12 obtain a result.

**Acceptance Scenarios**:

1. **Given** the platform is already running as many analyses as it can at once, **When**
   another user submits, **Then** the submission is accepted and shown as waiting, with its
   position in line and an estimated wait.
2. **Given** a waiting analysis, **When** analyses ahead of it finish, **Then** its position
   and estimate decrease, and it starts automatically when its turn comes.
3. **Given** 12 users submitting within the same minute, **When** all analyses have run,
   **Then** each of the 12 has a result (complete or with questions for them), and none got
   an error caused by the platform's load.
4. **Given** one user who already has the per-user maximum of analyses waiting or running,
   **When** they submit another, **Then** it is refused with a clear message asking them to
   wait for one to finish — so a single user can't push everyone else back in line.

---

### User Story 3 - Answer the pending questions, through the same queue (Priority: P1)

After a first run, a user answers the questions the AI couldn't. Resuming goes through the
same queue and status display as a first submission, so answering never fails because
others are using the platform either — and the resume only asks the AI about questions it
hasn't already answered for this analysis.

**Why this priority**: The human-in-the-loop round is part of every incomplete analysis;
if it still fails under load, the queue only solved half the problem.

**Independent Test**: Run an analysis that ends with pending questions, answer them while
other analyses are queued; confirm the resume is queued/shown like a submission, completes,
and that questions the AI had already answered were not sent to the AI again.

**Acceptance Scenarios**:

1. **Given** an analysis with pending questions and a busy platform, **When** the user
   submits their answers, **Then** the resume is accepted, shown as waiting/in progress,
   and the updated result appears when done.
2. **Given** a resume round, **When** it runs, **Then** questions the AI already answered
   earlier in this analysis are reused as-is and only newly revealed questions are sent to
   the AI.
3. **Given** a resume already waiting or in progress for an analysis, **When** the user
   submits answers again for the same analysis, **Then** the second submission is refused
   with a clear message instead of running twice.
4. **Given** a waiting resume, **When** it waits longer than the usual 30-minute window
   for answering questions, **Then** it is not lost: the window only counts time during
   which nothing is pending for that analysis.

---

### User Story 4 - Share the AI provider's quota gracefully (Priority: P2)

When many analyses run together, their questions to the AI provider are paced so the
platform stays within the free quota instead of hitting its limit and failing. Each
question also sends the provider less text than today where that doesn't change the
answer, so more analyses fit in the same quota.

**Why this priority**: Without pacing, running several analyses together turns into
provider-limit errors; without lighter questions, the queue moves slower than it needs to.
The queue (US2) still works without this, just more slowly and with more failures.

**Independent Test**: Run 12 analyses through the queue; confirm none fails because of the
provider's rate limit, and compare the text volume sent per question and the answers
obtained on reference projects against before this feature.

**Acceptance Scenarios**:

1. **Given** several analyses running at once, **When** their combined questions would
   exceed the provider's per-minute quota, **Then** questions are delayed until quota is
   available rather than sent and rejected.
2. **Given** the reference projects used during development, **When** they are analyzed
   after this feature, **Then** the answers and the questions escalated to the human are
   the same as before (no loss of answer quality from sending less text).

---

### User Story 5 - More analyses progressing at once on the same server (Priority: P3)

On the current server size, more analyses can be in progress simultaneously than the 2
allowed today, so the queue drains faster when the bottleneck is the server rather than
the provider (e.g. large projects being indexed).

**Why this priority**: Improves waiting times but isn't required for correctness — the
queue already guarantees everyone is served.

**Independent Test**: Run analyses in parallel on a server of the production size and
confirm at least 4 progress at the same time without running out of memory.

**Acceptance Scenarios**:

1. **Given** the production server size, **When** 4 analyses are in progress at once,
   **Then** all 4 complete and the server stays responsive (status pages keep updating).

---

### Edge Cases

- **Server restart / redeploy while analyses wait or run**: the uploaded material isn't
  kept (spec 005: the code is never stored), so they can't be continued. On startup, every
  analysis left waiting or in progress is marked failed with the reason "interrompue par un
  redémarrage du serveur — merci de relancer", never left spinning forever.
- **User closes the page while waiting**: the analysis keeps its place and runs; the result
  is in their history.
- **Queue extremely long**: the number of waiting analyses is bounded (well above 10 users
  × per-user limit) to protect server memory and disk; only beyond that bound is a
  submission refused, with a "platform saturated, retry in a few minutes" message.
- **Invalid submission** (no file, wrong format, too large, invalid PDF, invalid answer
  option): still rejected immediately at submission, before joining the queue — the queue
  never holds a request that is bound to fail.
- **Provider quota exhausted for a while**: analyses in progress slow down (wait for quota)
  rather than fail; an analysis fails only if the provider stays unreachable after retries.
- **A check fails midway**: its slot is released for the next one in line, and it is shown
  as failed with its reason (it no longer disappears silently as a failed run did before —
  the user submitted it and left, so they need to know).
- **Estimate accuracy**: the estimated wait is approximate (based on how long recent
  analyses took) and labeled as such; with no history yet, a default duration is used.
- **Another user's analysis**: status, position and results remain visible only to their
  owner (spec 005 FR-014), including while waiting.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST acknowledge a valid submission (new analysis or resume) without
  waiting for the analysis to run, and return an identifier the user can follow it by.
- **FR-002**: System MUST validate a submission fully (files, formats, sizes, PDF, answer
  options, session ownership) before accepting it into the queue, and reject invalid ones
  immediately with the same clear messages as today.
- **FR-003**: System MUST give every analysis a status among: waiting, in progress, done,
  failed — visible to its owner at any time, including from their history.
- **FR-004**: For a waiting analysis, System MUST expose its position in the queue and an
  estimated wait, derived from recent analysis durations.
- **FR-005**: System MUST run waiting analyses in submission order (first in, first out) as
  capacity frees up, with no manual action.
- **FR-006**: System MUST NOT refuse a valid submission because of platform load, except
  when the bounded queue is full (edge case above); it MUST NOT impose any per-request
  duration limit on the analysis itself.
- **FR-007**: System MUST limit each user to a small number of analyses waiting or in
  progress at the same time (default 2), refusing further ones with a clear message.
- **FR-008**: A resume with human answers MUST go through the same queue, statuses and
  limits as a first submission; a second resume for an analysis that already has one
  waiting or in progress MUST be refused.
- **FR-009**: The window in which pending questions can be answered (30 minutes) MUST NOT
  expire while a submission or resume for that analysis is waiting or in progress.
- **FR-010**: On a resume, System MUST reuse the AI's earlier answers for this analysis and
  only ask the AI about questions it has not answered yet.
- **FR-011**: System MUST pace all AI provider calls platform-wide so that the provider's
  per-minute request and token quotas are not exceeded, delaying calls rather than letting
  them be rejected.
- **FR-012**: System MUST reduce the amount of project text sent per question where this
  does not change answers on the reference projects (see US4 acceptance scenario 2).
- **FR-013**: System MUST allow more analyses to progress simultaneously than today (at
  least 4 on the production server size), by sharing resources that are currently
  duplicated per analysis.
- **FR-014**: When an analysis fails, System MUST record it as failed with a
  plain-language reason visible to its owner and free its capacity for the next one.
- **FR-015**: On startup, System MUST mark every analysis left waiting or in progress as
  failed with a "server restarted — please resubmit" reason.
- **FR-016**: The analysis page MUST refresh the status on its own while an analysis is
  waiting or in progress, show position/estimate while waiting, and show the result as
  soon as it is done, without the user reloading.
- **FR-017**: The history list MUST show each analysis's status (waiting, in progress,
  done, failed), so an analysis left running can be found and followed.
- **FR-018**: The uploaded material MUST still never be stored durably (spec 005 FR-009):
  it is kept only temporarily while its analysis waits or runs, and discarded afterwards
  or on failure.

### Key Entities

- **Analysis** (existing, spec 005): gains a status (waiting / in progress / done /
  failed), a failure reason, and timestamps for when it started and finished — so its
  owner can follow it and the platform can estimate waits. Created at submission time
  instead of after a successful run.
- **Queued job**: one unit of work waiting for or holding a slot — either a first run
  (with its temporarily-held uploaded material) or a resume (with the human answers). Lives
  only in the running server; its outcome is written to the Analysis.
- **AI answer memory** (per analysis session): the AI's answers already given for this
  analysis, reused on later resume rounds (lives with the existing in-memory session).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 12 users submitting an analysis within the same minute: 12/12 accepted, 0
  errors caused by load, 12/12 obtain a result.
- **SC-002**: A submission is acknowledged in under 5 seconds (excluding upload transfer
  time), whether the platform is idle or 12 analyses are already waiting/running.
- **SC-003**: A waiting user sees their position and estimated wait, refreshed at least
  every 10 seconds, and sees their result within 10 seconds of it being ready.
- **SC-004**: With 12 small-project analyses submitted together on the free provider
  quota, all 12 results are available within 10 minutes of the last submission.
- **SC-005**: 0 analyses fail because of the provider's rate limit during the 12-user test.
- **SC-006**: A resume round sends the AI only questions it had not answered before for
  that analysis (0 repeated questions), measured on a two-round analysis.
- **SC-007**: Text sent to the AI per question is reduced by at least 30% on a real
  project, with identical answers and escalations on the reference projects.
- **SC-008**: At least 4 analyses progress simultaneously on the production server size
  (2 vCPU / 8 GB) without memory exhaustion, versus 2 today.
- **SC-009**: An analysis taking longer than 5 minutes completes and shows its result
  instead of a timeout error.

## Assumptions

- Single backend instance (current production setup): the queue, the running analyses and
  the resumable sessions live in that one server's memory. Horizontal scaling (several
  instances) is out of scope and would need shared storage for all three; the deployment
  must stay at one instance.
- Stay on the provider's free tier (100 requests/min, 100,000 tokens/min, measured
  2026-09-27). If the quota is raised later (paid tier), pacing adapts to the provider's
  reported limits without changes.
- "Reference projects" for answer quality (US4, SC-007) are this repository's own backend
  code, the PDF/code combination used to validate spec 006, and a code-only sample project
  — the same inputs used for live verification in earlier specs.
- Losing waiting/running analyses on a restart is acceptable (they are marked failed and
  the user resubmits), since keeping uploaded material across restarts would contradict
  the "code is never stored" principle.
- Polling-based page updates (the page asks for the status every few seconds) are
  sufficient; no push/real-time channel is needed at this scale.
- Default limits: 2 analyses per user waiting or running; queue bounded at 50 waiting
  analyses; parallelism set by configuration with a default of 4 — adjustable without code
  changes.
