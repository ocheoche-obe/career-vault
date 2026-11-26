# CareerVault: fresh-eyes review

**Date:** 2026-11-16 · **Branch reviewed:** `feat/v1.1-slice5-resume-speed` (PR #52, 7 commits ahead of `main`)

**How this was done.** I read the code, README, docs, SAM template, CI config and git history, and
ran the free suites. I did not have AWS access (the SSO session was expired), so nothing here was
checked against the live stack: corpus size, spend and latency figures are the ones recorded in the
repo, the newest of which is from 2026-08-21. One caveat on "fresh eyes": the session loads
`CLAUDE.md` automatically, so I had seen the old file before I started. I worked from the code and
did not consult it until step 4, but it was not a blind read.

**What I verified myself:** 429 backend unit tests and 267 frontend tests pass, `npm run build` and
`npm run lint` are clean, and CI is green on PR #52.

> **Update, 2026-11-26.** Done since this review: §4 item 0 (PR #52 merged, README counts dropped
> in #74, most Dependabot PRs merged; #58, #66 and #68 are still open) and all of item 1: table, data
> bucket and user pool protection (#73), résumé worker retries off with a re-entry guard (#75), and
> CORS on gateway errors with sign-in on a 401 (#75, B-041). That also closes risks 1, 2, 3 and 5 in
> §2 and items 1 to 3 of "What I would change first". Item 5 there is partly done by ADR-049: an ADR
> only for decisions expensive to reverse, and status only on the plan's status board, which settles
> the `/wrap-slice` conflict in §5. The rest of the review is unchanged and still dated 2026-11-16.

---

## The short version

The engineering is good. The product has stalled, and I think the two are related.

- There have been no commits since 2026-08-21. PR #52 has sat open and green for 87 days, and ten
  Dependabot PRs have queued up behind it.
- The last five slices were three redesign slices, voice input and résumé speed. None of them gave
  you a reason to open the app more often, and the corpus was 13 entries when last measured in August.
- The repo holds about 111,000 words of documentation for about 6,300 lines of backend Python.
  Every slice carries an ADR, completion notes, an explainer, two reviews and a status update in
  four places. That is a lot of ceremony for an app with one user, and I suspect it is a large part
  of why picking it back up feels heavy.

My recommendation is to stop polishing what exists and spend the next few slices on capture: make
the app come to you, ask good questions, and turn a loose answer into several well-formed entries.
Everything else the app does is limited by how much is in the corpus.

---

## 1. The idea

### What is strong

- **The problem is real and it is yours.** People forget what they did, and the cost shows up at
  review time and at job-hunt time. A record built as things happen is worth more than one
  reconstructed later.
- **The trust model is right.** The model proposes, you confirm, and only then is anything saved.
  The résumé agent may only use facts from your entries. For a document you will put your name on,
  that is the property that matters most.
- **The accumulated corpus is the asset.** A general assistant can tailor a résumé from a pasted
  document. It cannot remember the award you mentioned in March. That memory is the only thing here
  a chat window does not already give you.
- **Cost discipline is real.** $3.88 in the heaviest month against a $5 ceiling, with every
  operation measured.

### What is weak

- **Capture is the bottleneck and almost nothing has been spent on it.** The corpus was 13 entries
  when it was last measured, in August. Chat turns one message into exactly one entry. The check-in
  email is the only thing that pulls you back, and it links to the app's front page rather than
  asking a question you can answer on the spot.
- **The payoff is rare.** A tailored résumé is something you need a few times a decade. An app whose
  main output is needed that rarely will not hold a habit, however fast the output is.
- **The résumé on its own is not differentiated.** With 13 entries, pasting your history and a job
  description into any assistant gets most of the way there in one call. The six-phase agent only
  earns its keep once the corpus is too large to paste.
- **Recent effort went to polish.** The redesign, dark mode, dictation and the 41% speed-up are all
  well executed. None changes whether the app is worth opening on a Tuesday.

### Three directions

**A. The app interviews you (capture comes to you).**
Make logging a conversation the app starts and leads.

- A brain dump ("this month I shipped X, passed Y, mentored Z") becomes several proposed entries,
  each confirmed or discarded.
- After a thin entry, the app asks one follow-up aimed at impact: what changed, by how much, who
  noticed. This is where the résumé bullets actually come from.
- The check-in email asks one specific question drawn from your recent entries, and its link lands
  in the composer with that question waiting.
- Later, and only if the above works: reply to the email to log. This needs inbound email, which
  needs a domain you own. See "needs your call" below.

This is more AI in the loop in the place it helps most, and it runs on Haiku, so it costs cents.

**B. More outputs from the same corpus.**
Give the corpus a payoff every quarter, not every few years.

- A self-review or brag document for a date range.
- A gap analysis against a target role (B-030 already wants this, and you have a stated target:
  solutions architect).
- Interview preparation: STAR stories drawn from your entries for common questions.

Each is a new prompt and template on top of the existing draft step. The risk is that with a thin
corpus every output is thin too.

**C. Make the corpus available to other assistants (an MCP server).**
Expose "log an entry", "search my history" and "get my profile" as tools, so you can say "log this"
in whatever assistant you are already working in. The calling model does the structuring, so the
Bedrock cost is close to zero, and it is a directly relevant thing to have built for a solutions
architect path. The hard part is auth: Cognito does not support the dynamic client registration
that remote MCP clients expect, so this needs a design spike before it is a slice.

### My pick: A

Directions B and C both get better the more is in the corpus, and A is what fills it. A also has the
cheapest honest test: build the multi-entry brain dump and the follow-up question, use it for three
weeks, and see whether the entry count moves. If it does not, the idea has a habit problem that no
feature fixes, and that is worth knowing before building B or C.

C is my runner-up and the most interesting to build. I would do the spike after A's first two
slices.

---

## 2. Design and architecture

### What is solid

- **The shape fits the problem.** Seven small Lambdas, one DynamoDB table, S3 and CloudFront, all in
  one SAM template. Idle cost is under a cent a month.
- **Privilege separation in chat.** The routing call has tools but never sees entry content. The
  answering call sees entry content and has no tools. The chat Lambda cannot create entries at all.
  This is a real prompt-injection defence and it is documented where it is enforced.
- **The résumé agent is properly bounded.** Token ceiling, wall-clock ceiling, iteration caps,
  stagnation detection, and expected failures returned as statuses, not exceptions.
- **Async job plus poll** is the correct answer to API Gateway's 29-second limit, and the ordering
  of the non-transactional writes is reasoned through in each place.
- **One Bedrock wrapper** owns retries, with the SDK's own retries switched off so the two layers
  cannot multiply.
- **Tests are tiered by cost,** so the default run is free and takes seconds.

### What is risky

1. **The table holding your only copy of the data is not protected.** Deletion protection and the
   retain policies are keyed on `Environment=prod`, but ADR-041 made the dev stack the real one.
   A `sam delete`, or a template change that replaces the table, removes it. Point-in-time recovery
   is on, so there is a recovery window, but the guard should match where the data lives.
2. **A crashed résumé worker can be re-run twice, at full cost.** The worker is an async
   self-invocation, the function has no `EventInvokeConfig`, and Lambda's default for async
   invocations is two retries. The worker does not check whether the run has already started. An
   unhandled exception or a 300-second timeout would therefore run the Sonnet agent up to three
   times for one click. I found this by reading the template and handler; I have not reproduced it.
3. **Returning after a break looks like an outage.** An expired session surfaces as a CORS error
   (B-041), because API Gateway's default 4XX responses carry no CORS header. After three months
   away, this is the first thing you will hit.
4. **The ID token is kept in `localStorage` and the site ships no CSP (B-038).** Either alone is
   tolerable. Together, any script injection is a token theft. Chat answers are rendered as plain
   text to limit this, which is a rule that has to be remembered forever in place of a header that
   would enforce it.
5. **The dev stack is running code that is not on `main`.** Slice 5 was deployed and verified but
   PR #52 was never merged. Anyone, or any agent, deploying from `main` would roll it back.

### What is overbuilt

1. **Agentic retrieval over a corpus that fits in one prompt.** The agent runs a Haiku analysis
   call, then up to eight Sonnet tool-use turns with embedding searches, to choose among 13 entries
   that would fit in the draft prompt several times over. B-004 records this loop as the dominant
   cost of a run. Slice 5 made the loop cheaper with caching; the larger saving is to skip it
   whenever the whole corpus is under a token threshold and hand every entry to the draft step.
   The loop stays for the day the corpus outgrows the threshold. I expect this to cut both time and
   cost substantially, but that is a prediction and it needs measuring on the real corpus, which
   has not been re-measured since before slice 5 (B-048).
2. **Embeddings travel with every read.** Each entry carries a vector of about 20 KB, and every
   entry list, chat answer, check-in and résumé run reads all of them. It is harmless at 13 entries
   and it is the reason the docs keep returning to B-013. If the résumé path stops needing vectors
   for small corpora, the remaining users are chat Q&A and duplicate detection.
3. **Scaffolding for a prod stack that cannot deploy.** A `[prod]` config block, prod-only billing
   alarms that have never existed, and prod-only data protection, all for an environment that
   ADR-041 decided against and B-021 says cannot be created. Either delete it or fix B-021. Keeping
   it half-alive is how risk 1 above came about.
4. **The process.** 47 ADRs, including two about colour tokens. A plan document of 2,269 lines. A
   backlog whose 49 rows average over a thousand characters each. A wrap ritual that blocks on two
   reviews, an explainer page and updates to five documents. The same test counts written in four
   places, already out of step: the README says 376 backend and 23 frontend tests, and the real
   numbers are 429 and 267. The documents are honest and often insightful. They are also now the
   biggest thing in the repo, and for a learning project the learning is in the ADR's decision, not
   in the fourth restatement of it.

### What I would change first

1. Protect the data: turn on deletion protection and a retain policy for the table and data bucket
   regardless of environment.
2. Set the résumé function's async retries to zero and have the worker refuse a run that is no
   longer `pending`.
3. Return CORS headers on gateway 4XX responses and send the user to sign-in on a 401.
4. Add the small-corpus fast path to the résumé agent and measure it.
5. Cut the ceremony. My suggestion: an ADR only when a decision would be expensive to reverse,
   completion notes capped at a screen, counts and status in exactly one place, and the explainer
   only when you ask for one.

Items 1 to 3 are one small slice and one deploy.

---

## 3. Code health

### Good

- **Everything is green and fast.** 429 backend tests in under a second, 267 frontend tests in
  about three, clean build and lint, zero `TODO` or `FIXME` markers.
- **Tests assert behaviour that matters,** for example a request count over elapsed time for the
  runaway poll loop, and the confirm gate's 409 path. The habit of breaking code to prove a test
  notices is the right one.
- **Handlers are consistent:** identity from the JWT, validation with Pydantic, scoped DynamoDB
  helpers, the same response shape, metrics on every outcome.
- **Dependencies are few.** The frontend has four runtime dependencies and no router or state
  library.

### Gaps

- **No browser test of the assembled app.** Component tests and API tests are thorough; the path
  from sign-in to a saved entry is verified by hand. One Playwright smoke test against the dev
  stack, run on demand, would cover the failure that unit tests cannot see.
- **Integration tests are local-only and need a live SSO session,** so they have not run since
  August. B-025 also records that a misconfigured environment produces a green run that executed
  nothing.
- **Deploys are manual from a laptop** with no record of what is deployed. That is how the stack
  and `main` drifted apart.
- **Model IDs are pinned to mid-2026.** Sonnet 4-6 and Haiku 4.5 will not be available forever, and
  the Sonnet 5 entitlement (B-010) was last probed in July. It is worth one re-check, since it was
  recorded as about a third cheaper per token.
- **Ten Dependabot PRs are open,** the oldest from 2026-09-01. The project has a triage skill for
  exactly this.

### Fragile

- **Comments carry history.** A large share of each backend file is commentary, and much of it
  narrates how the code got here: slice numbers, backlog IDs, what an earlier version did wrong.
  The reasoning is valuable. Embedded in the code, it goes stale silently, and it makes the files
  slow to read. The ADL is the right home for it.
- **Prompt-injection safety in chat rests on two conventions:** no tools on the synthesis call,
  and plain-text rendering in the client. Both are documented and both are pinned by a test, which
  is the right treatment. A CSP would make the second one enforceable instead of remembered.
- **Two test helper modules with the same function names and different signatures** are on the path
  at once (B-026).
- **CI and the local rule disagree.** The project says never to run `python -m pytest` directly,
  and CI does exactly that. It works because CI installs the dev requirements globally. It is worth
  a comment in the workflow so nobody "fixes" it.
- **`GET /resumes` silently caps at 50** with no cursor (B-043). Not urgent at current volume.

---

## 4. Next steps

Ordered. Each numbered item is one slice. Item 0 is an hour of housekeeping, not a slice.

| # | Slice | Size | Why now |
|---|---|---|---|
| 0 | Merge PR #52, triage the ten Dependabot PRs, correct the README test counts | 1 hour | `main` should match what is deployed before anything else changes |
| 1 | **Safe to come back to.** Table and bucket protection in dev; résumé worker retries off plus a re-entry guard; CORS on gateway 4XX and redirect to sign-in on 401 (B-041) | Small, one deploy | Removes the one data-loss risk, the one cost-runaway risk, and the first thing a returning user hits |
| 2 | **Résumé fast path.** Skip analysis and retrieval when the corpus is under a token threshold; re-measure on the real corpus (closes B-048) | Small, about $0.50 of runs | Likely the largest remaining cost and latency win, and it simplifies the common path |
| 3 | **Brain dump and follow-up.** One message can yield several proposed entries; a thin entry gets one impact question. Give the parse turn a compact list of existing jobs so projects can link to them (closes B-044) | Medium | The core of direction A, and the test of whether capture is fixable |
| 4 | **Check-in that asks a question.** The email poses one specific question; its link opens the composer with that question in place. Record entries per week before and after | Small to medium | Tells you whether the app can pull you back |
| 5 | **Second output: self-review for a date range.** New template and prompt on the existing draft step | Medium | A payoff that recurs quarterly; only worth doing if slice 3 and 4 grew the corpus |
| 6 | **Decision point.** Reply-by-email (needs a domain) or an MCP server (needs an auth spike). Pick one based on how slices 3 and 4 went | Spike first | Both are larger; neither should start on a guess |

What I would drop from the current plan:

- **The UI and mobile pass as a slice.** 28 emulated combinations already show no overflow. What
  remains for NFR-6.2 is opening the app on your phone for ten minutes. Do that during slice 1.
- **B-047 (cold start).** A 2.6-second first load on an app opened weekly is not what stands
  between you and using it.
- **Further résumé styling and format options (B-009)** until there is more in the corpus to style.

---

## 5. What changed in CLAUDE.md

I wrote the new `CLAUDE.md` from the code, then compared it with the old one (`main:CLAUDE.md`, and
the slice 5 revision of it on this branch). The file went from about 290 lines to about 140.

### Carried over after the comparison

These were in the old file, are still true, and were missing from my first draft.

| Item | Why it stays |
|---|---|
| The sort-key prefixes for each item type, in one line | Saves a lookup on almost every backend task |
| Which model does which job (Haiku everywhere except résumé retrieval and drafting) | It is the cost model in one sentence |
| Sonnet 5 was blocked on this account (B-010) | Stops a session from burning time re-probing. I softened "stop probing" to "ask first", since the last attempt was in July |
| The secret-handling rule (never read secret values into the conversation) | A safety rule you set. Kept, compressed to three lines |
| Check the AWS MCP server for a relevant skill | One clause |
| A zero-overflow assertion does not prove a mobile layout | A trap that already shipped a bug once |

### Already covered by both

The dev stack is the live one and prod cannot deploy; the AWS profile and account check; the $5
ceiling and what spends money; user ID from the JWT; scoped DynamoDB helpers and the IAM limit behind
them; the Bedrock traps (`required` is a hint, temperature 0 varies, `cachePoint` no-ops silently,
inference-profile pricing); the 29-second limit; permanent résumés and the delete order; the theme
script; the `useEffect` poll loop; dictation never submits and discloses third-party processing;
`related_job_id`; the design handoff rule; colours only in `index.css`; stub `fetch` in tests;
`npm test` does not typecheck; break the code to prove a test; use the slice skills.

### Dropped, and why

| Dropped | Why |
|---|---|
| The "Current phase" section (about 90 lines of slice 3, 4 and 5 history) | It is a changelog. The lasting lessons are now one line each under Gotchas; the history is in the plan and the ADL. It was also the part most likely to be stale |
| Test counts | Written in four places and wrong in at least one. The suites print their own |
| Architecture summary, Lambda list with descriptions, layer details, repository tree | One read of the template and the folder names gives the same thing. A short layout block remains |
| Python conventions (handler signature, use boto3, use Powertools) | Every handler already shows the pattern |
| Requirement and architecture section numbers | Not needed to find things; search by ADR or backlog ID |
| Per-operation costs for chat and check-in, budget alert thresholds, log retention | Too small to change a decision. The résumé cost range stays because it does |
| "Caching was the wrong lever", "cold start is not B-013", the measured latency breakdowns | True and interesting, and they belong to ADR-047 and ADR-048 |
| Hard delete, no GSIs, PITR, encryption settings | Visible in the template; none is a trap |
| "Follow Well-Architected principles" and "prefer infrastructure as code" as general advice | The second survives as a concrete rule (changes go in the SAM template) |
| The remaining-scope list for v1.1 | Status, and this review proposes changing it |

### Two things that changed meaning

- The old file said the dev stack is the MVP and left it there. The new one says to treat it as
  production, because that is where the data is and the template does not protect it yet.
- The old file told the reader to write an ADR for any decision the architecture doc does not
  cover. The new one says to write one when the decision would be expensive to reverse. This is a
  process change and it is yours to accept or revert.

### One conflict to resolve

`/wrap-slice` treats an up-to-date phase marker in `CLAUDE.md` as blocking. The new file has no phase
marker and points to the plan's status board instead. I could not edit the skill in this session.
Either the skill's step should point at the status board, or a short marker goes back in.
