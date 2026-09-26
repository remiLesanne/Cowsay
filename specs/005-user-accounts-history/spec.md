# Feature Specification: User Accounts and Per-User Analysis History

**Feature Branch**: `feature/user-accounts-history`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "User accounts and per-user analysis history. Users must
create an account (email + password) and log in to run an EU AI Act compliance check;
running an analysis anonymously is no longer possible. Every compliance check a
logged-in user runs is saved automatically: file name, a fingerprint (hash) of the
project content (never the code itself), optional company name, the checker's verdict,
whether the form is complete, the per-question detail (question, chosen answer,
reasoning, AI or human source), and the questions still awaiting a human answer. A user
can list their past analyses and open any of them again, including incomplete ones, and
can only see and resume their own. Minimal auth: register, login, logout, current user.
Also fix free-text human answers being silently dropped on resume. Out of scope: a
shared cross-user result cache, deployment."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an account and log in (Priority: P1)

A new visitor creates an account with their email and a password, then logs in. Once
logged in, they can see which account they're using and log out. A visitor who is not
logged in and tries to reach the analysis tool is sent to the login page instead.

**Why this priority**: Every other part of this feature (running a check, history)
depends on knowing who the user is. Requested by the team as the most urgent item.

**Independent Test**: Register a new email, log out, log back in with the same
credentials, confirm the account's email is displayed; try logging in with a wrong
password and confirm it is refused.

**Acceptance Scenarios**:

1. **Given** an email with no existing account, **When** the visitor registers with that
   email and a valid password, **Then** the account is created and the visitor is logged
   in.
2. **Given** an existing account, **When** someone registers again with the same email
   (any letter case), **Then** registration is refused with a clear message and no
   second account is created.
3. **Given** an existing account, **When** the user logs in with a wrong password or an
   unknown email, **Then** login is refused with the same generic message in both cases
   (no hint about which part was wrong).
4. **Given** a logged-in user, **When** they log out, **Then** they can no longer run a
   check or see their history until they log in again.
5. **Given** a visitor who is not logged in, **When** they open the analysis page or the
   history page, **Then** they are redirected to the login page.

---

### User Story 2 - Run a compliance check that is saved automatically (Priority: P1)

A logged-in user uploads their project as today. The check runs exactly as before
(same checker, same AI answers, same human-in-the-loop questions), and the result is
saved to their account without any extra action. Each time they answer pending
questions and the check resumes, the saved record is updated with the new state. The
result now also shows, question by question, what was answered, why, and whether the
answer came from the AI or from the user.

**Why this priority**: Running the check is the core value of the product; making it
account-bound and persistent is what the history (US3) is built on.

**Independent Test**: Log in, upload a small project, confirm the result screen shows
the verdict plus the per-question detail; answer a pending question and confirm the
detail now lists that question with the user as source; confirm the saved record
reflects the latest state (see US3).

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** they upload a project, **Then** the check runs
   and a saved analysis is created holding the file name, the project fingerprint,
   the optional company name, the verdict, the completeness status, the per-question
   detail and the pending questions.
2. **Given** a saved incomplete analysis whose session is still active, **When** the
   user answers the pending questions, **Then** the same saved analysis is updated
   (not duplicated) with the new verdict, status, detail and pending questions.
3. **Given** a pending question that expects free text, **When** the user submits a
   text answer, **Then** that answer is used when the check resumes and the question
   does not come back as pending (bug fix: today such answers are silently dropped).
4. **Given** a request to run or resume a check without being logged in, **When** it
   reaches the system, **Then** it is refused and nothing runs.
5. **Given** user A's check session, **When** user B tries to resume it, **Then** the
   request is refused as if the session did not exist, and user A's analysis is
   unchanged.

---

### User Story 3 - Review past analyses ("Mes analyses") (Priority: P2)

A logged-in user opens "Mes analyses" and sees the list of every analysis they ran,
most recent first, with file name, date and status (complete / incomplete). Opening one
shows the full saved result again: verdict, per-question detail and pending questions.

**Why this priority**: The team asked for a history that gives back the form result for
an already-analyzed project without redoing the analysis; it depends on US1 and US2.

**Independent Test**: Run two checks on two projects, open "Mes analyses", confirm both
appear newest first; open the older one and confirm its verdict and detail match what
was shown when it ran; log in as a different user and confirm neither appears.

**Acceptance Scenarios**:

1. **Given** a user with several saved analyses, **When** they open "Mes analyses",
   **Then** they see all of their analyses and only theirs, newest first.
2. **Given** a saved analysis, **When** the user opens it, **Then** they see the same
   verdict, completeness status, per-question detail and pending questions as at the
   end of its last run, without the check being run again.
3. **Given** an analysis belonging to another user, **When** a user tries to open it
   (e.g. by guessing its address), **Then** access is refused as if it did not exist.
4. **Given** a user with no analyses yet, **When** they open "Mes analyses", **Then**
   they see an empty state inviting them to run a first analysis.

### Edge Cases

- **Resume after the session expired**: the saved analysis stays viewable, but its
  pending questions can no longer be answered in place (the processed project is only
  kept for a limited time, see spec 003). The user is told to upload the project again,
  which creates a new analysis.
- **Server restart**: saved analyses and accounts survive; in-progress sessions do not
  (same trade-off as spec 003).
- **Check fails midway** (AI service down, checker site unreachable): no analysis is
  saved for that attempt, the user sees the existing error message, and a previously
  saved analysis being resumed keeps its last good state.
- **Login expires** while the user is on a page: the next action that needs the account
  sends them back to the login page with a message.
- **Same project uploaded twice**: two separate analyses are saved (both carry the same
  fingerprint); reusing a previous result is out of scope.
- **Invalid registration input** (malformed email, password too short): refused with a
  message saying what to fix.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let a visitor create an account with an email address and a
  password of at least 8 characters; emails are unique regardless of letter case.
- **FR-002**: System MUST let a registered user log in with their email and password
  and log out; a failed login MUST NOT reveal whether the email exists.
- **FR-003**: System MUST never store passwords in a recoverable form.
- **FR-004**: System MUST expose who the currently logged-in user is, so the interface
  can display it.
- **FR-005**: A login MUST expire after a bounded period, after which the user must log
  in again.
- **FR-006**: Running a compliance check and resuming one MUST require a logged-in user;
  anonymous requests are refused before any analysis work starts.
- **FR-007**: System MUST save an analysis record automatically for every successful
  check run, linked to the user who ran it.
- **FR-008**: The analysis record MUST contain: file name, content fingerprint, company
  name (if given), verdict text, completeness status, per-question detail, pending
  questions, creation date and last-update date.
- **FR-009**: System MUST NOT store the uploaded project's code or files; only the
  fingerprint derived from them.
- **FR-010**: The check result returned to the user MUST include the per-question detail:
  question text, answer given, reasoning, and source (AI or user).
- **FR-011**: Each resume round MUST update the same analysis record rather than create
  a new one.
- **FR-012**: A free-text answer submitted for a pending question MUST be applied when
  the check resumes, exactly like a multiple-choice answer.
- **FR-013**: Users MUST be able to list their own analyses, newest first, and open any
  of them to see the saved result without re-running the check.
- **FR-014**: A user MUST NOT be able to see, open or resume another user's analysis or
  session; such attempts are answered as "not found".
- **FR-015**: The interface MUST send visitors who are not logged in to the login page
  when they try to use the analysis tool or the history.

### Key Entities

- **User account**: an email (unique, case-insensitive), a protected password, a
  creation date. Owns zero or more analyses.
- **Analysis**: one compliance check of one uploaded project by one user. Holds the file
  name, content fingerprint, optional company name, verdict text, completeness status,
  list of question details, list of pending questions, created/updated dates. Linked to
  the in-progress check session while that session is alive.
- **Question detail**: one question the checker asked during the analysis — question
  text, answer given (one or several options, or free text), reasoning, source (AI or
  user).
- **Pending question** (unchanged from spec 003): a question the AI couldn't answer
  confidently, with its options when it is multiple-choice.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can go from the home page to a logged-in account in under 1
  minute.
- **SC-002**: 100% of successful check runs by a logged-in user appear in that user's
  history, with the same verdict as shown at the end of the run.
- **SC-003**: Reopening a saved analysis displays its result in under 2 seconds, with no
  re-run of the check.
- **SC-004**: In a two-account test, 0 analyses of one account are visible or resumable
  from the other.
- **SC-005**: A pending free-text question answered by the user does not come back as
  pending on the next round (0 silently dropped answers).
- **SC-006**: Running a check takes no noticeably longer than before this feature (saving
  adds under 1 second).

## Assumptions

- No email verification, password reset, roles or admin screens (explicit minimal
  scope); the product is a school project demonstrated by the team.
- The login lasts 24 hours before expiring; the interface keeps the user logged in
  across page reloads during that time.
- Accounts and analyses are stored in the relational database already planned in the
  README (local PostgreSQL for development, managed PostgreSQL such as Supabase/Neon
  once deployed, selected through configuration); deployment itself is out of scope.
- The in-memory check session from spec 003 is kept as-is (30-minute lifetime); only
  the analysis *record* is persisted, not the processed project needed to resume.
- The fingerprint is computed from the project's content so that the same project
  yields the same fingerprint; it is stored now so a future "this project was already
  analyzed" shortcut can reuse it (out of scope here).
- The existing bare-bones test page (`/compliance`) follows the same rule: it requires
  a logged-in user.
