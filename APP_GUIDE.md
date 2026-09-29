# Incident Intelligence Platform: the plain-English guide

> **What this file is.** A complete, easy-to-read tour of the app: what it does, *why* it does it,
> every screen, every test case, and what the numbers mean.
> **Who it is for.** Anyone. You do not need to know how to code.
>
> **How much of this did I actually check?**
> - **Observed** = I ran it against your live API on 2026-09-29 and copied the real result.
> - **From code / tests** = read from the source code or the automated tests, but not clicked by hand.
> - Every test case below is marked one or the other, so you know how far to trust it.

---

## Contents

1. [What is this app? (the 60-second version)](#1-what-is-this-app-the-60-second-version)
2. [Words you will see](#2-words-you-will-see)
3. [Start the app](#3-start-the-app)
4. [The big picture](#4-the-big-picture)
5. [What happens when you click Analyze (step by step, with the why)](#5-what-happens-when-you-click-analyze)
6. [Screen-by-screen tour](#6-screen-by-screen-tour)
7. [Guided troubleshooting: the rules](#7-guided-troubleshooting-the-rules)
8. [Escalation: handing the problem to a senior engineer](#8-escalation-handing-the-problem-to-a-senior-engineer)
9. [How the app learns](#9-how-the-app-learns)
10. [Live correlation: spotting one big outage hiding in many tickets](#10-live-correlation)
11. [Safety nets](#11-safety-nets)
12. [Test cases you can run by hand](#12-test-cases-you-can-run-by-hand)
13. [The automated tests, explained](#13-the-automated-tests-explained)
14. [The report card numbers in plain English](#14-the-report-card-numbers-in-plain-english)
15. [Honest limits](#15-honest-limits)
16. [Why did it do that? (FAQ)](#16-why-did-it-do-that-faq)
17. [Appendices: API list, file map, settings](#17-appendices)

---

## 1. What is this app? (the 60-second version)

**The situation.** Something breaks at work: "the app is slow", "I can't log in", "the printer is dead".
The person helping (an IT support engineer) needs four answers, fast:

| Question | What the app gives them |
|---|---|
| Has this happened before? | It searches about **3,130 past incidents** |
| What fixed it last time? | **One** recommended first step, with the proof behind it |
| What if that fails? | Guided next steps, and it never repeats a failed one |
| Who takes over if nothing works? | A hand-off note (an "escalation packet") for a senior engineer |

**A good way to picture it:** a very experienced colleague who has read every past ticket. You describe the
problem. They say: "This looks like the *memory leak* problem we've seen many times. Restarting the service
worked most often. Here are the tickets that prove it." If they have *never* seen anything like it, they say
so honestly instead of guessing.

```
   You type:                       The app answers:
 +---------------------------+     +--------------------------------------------+
 | "The application is       |     |  KNOWN PATTERN  (blue)                     |
 |  slower and sometimes     | --> |  Family F001: memory leak / heap exhaustion|
 |  freezes. Restarting      |     |  Try first: Restart the application service|
 |  fixes it for a while."   |     |  Confidence 0.45  (worked out, not guessed)|
 +---------------------------+     |  Backed by 5 past incidents                |
                                   +--------------------------------------------+
```

**Three promises the app makes** (you can test all of them, see [Section 12](#12-test-cases-you-can-run-by-hand)):

1. **Evidence before opinion.** Every recommendation shows the past incidents behind it.
2. **"I don't know" is a real answer.** If nothing similar exists, it says **Novel incident** and does *not* invent a fix.
3. **A human stays in charge.** It never touches a real system. Risky steps (restart, delete) are marked "needs human confirmation".

---

## 2. Words you will see

| Word | Plain meaning |
|---|---|
| **Incident** | One reported problem ("VPN keeps dropping"). |
| **Knowledge base (KB)** | The library of past incidents (3,130 records) the app searches. |
| **Pattern family** | A group of past incidents that are really the same problem in different words. There are **30** (F001 to F030). Example: F001 = *memory leak / heap exhaustion*. |
| **Fingerprint** | A short "ID card" the app pulls out of your text: component, symptom, failure type, trigger, root cause, environment, and so on. Unknown fields stay `Unknown`; it never makes them up. |
| **Known pattern / Novel incident** | *Known* = looks like a family we have seen. *Novel* = nothing similar enough. |
| **P(known)** | "Probability this is a known problem." A number from 0 to 1. Compared with a cut-off of **0.4896**. Below the cut-off means Novel. |
| **Confidence** | How sure the app is about its *first fix*. It is a calculation (see [5.7](#57-the-confidence-number-worked-example)), never a guess by an AI. |
| **Strategy** | One *way of fixing* a problem, such as "restart the service" or "increase the heap size". A family usually has 2 or 3. |
| **Provenance** | "Where did this fact come from?" Tags: **original** (straight from real data), **derived** (worked out from real data by a fixed rule), **synthetic** (text written by an AI from real ticket details), **inferred** (a best guess), **missing**. |
| **Synthetic** | About **95%** of the library's *text* was written by a small AI from real ticket facts, because the real tickets had no descriptions. It is always labelled, and it counts a bit less (x0.8). |
| **Retrieval-only mode** | The app is running without an AI writer. Everything shown comes from past incidents and maths. A band says so. |
| **Escalation** | Handing the problem to a more senior engineer. |
| **L1 / L2 / L3** | Support tiers. L1 = first line, L2 = specialists, L3 = deepest experts. The order is configurable. |
| **Attempt** | One suggested step and what you answered: **WORKED**, **FAILED** or **UNKNOWN** ("Not sure"). |
| **Evidence chain** | The "why did you say that?" trail: what was understood, what family matched, which incidents were used, how strong the evidence is. |
| **Correlation** | Several tickets in a short time that are really one big outage. |
| **Hybrid search** | Two searches at once: one by **meaning**, one by **keywords**. Results are then merged. |

---

## 3. Start the app

You need **two terminals**, both opened in the project folder.

```
 Terminal 1: the engine (API)              Terminal 2: the screens (website)
 ---------------------------------         ---------------------------------
 venv\Scripts\activate                     cd web
 uvicorn backend.main:app --port 8000      npm install      (first time only)
                                           npm run dev
 wait for:
   "Application startup complete"          then open  http://localhost:3000
 (first start takes about a minute
  because it loads its models)
```

> Your folder contains a `venv` folder (not `.venv`). The older docs say `.venv`; use whichever exists.

**How to know it is healthy.** Open <http://localhost:8000/health>. When I checked, it said:

| Part | Result I saw |
|---|---|
| status | `ok` |
| Search engine (ChromaDB) | `embedded ok (3130 vectors)` |
| Meaning-model (embeddings) | local `all-MiniLM-L6-v2` |
| Re-ranker | local `ms-marco-MiniLM-L-6-v2` |
| Knowledge base | 3,130 records, 30 families |
| Calibration | cross-encoder: yes, novelty: yes |
| Escalation tiers | L1, L2, L3 |
| AI writer (LLM) | `available: true`, model `gpt-4o-mini` (an AI key is set on this machine) |

The bottom of the left menu in the website shows the same status. If the engine is off, **every screen shows
"Could not load this view."**

**Desktop only.** The website needs a window at least 1200 px wide. There is no phone layout.

---

## 4. The big picture

The app has three "floors": data that was prepared once, the engine that answers questions, and the
screens you click.

```
 FLOOR 1: PREPARED ONCE (offline)
 +-----------------------------------------------------------------------+
 |  Two raw data files  ->  clean up  ->  add AI-written text  ->        |
 |  quality check  ->  find 30 families  ->  build search indexes        |
 |  (46,606 real tickets, 3,130 of them turned into searchable records)  |
 +-----------------------------------------------------------------------+
                                   |
                                   v
 FLOOR 2: THE ENGINE (FastAPI, port 8000)             <- answers questions
 +-----------------------------------------------------------------------+
 |  Understand -> Search -> Re-rank -> Fingerprint -> Family -> Known?    |
 |  -> Pick ONE fix -> Safety check -> Explain (evidence chain)           |
 |  + Guided troubleshooting + Escalation + Correlation + Learning        |
 +-----------------------------------------------------------------------+
                                   ^
                                   | (plain web requests)
 FLOOR 3: THE SCREENS (Next.js website, port 3000)
 +-----------------------------------------------------------------------+
 |  Assistant | Troubleshooting | Escalations | Novel incidents |         |
 |  Patterns | Knowledge base | Feedback | Evaluation                     |
 +-----------------------------------------------------------------------+
```

### The life of one incident

```
   (1) Report it                 (2) Analyze
   "app is slow..."   ------->   known or novel? which family? first fix?
                                        |
                          +-------------+--------------+
                          |                            |
                     KNOWN PATTERN                 NOVEL INCIDENT
                          |                            |
                (3) Guided troubleshooting     "No playbook" -> fresh
                    try a step                  investigation, escalate
                    /     |      \                      |
              WORKED   FAILED   NOT SURE                |
                |        |         |                    |
                |   next-best step (never a            |
                |   failed one again)                  |
                |        |                             |
                |   3 fails? -> ONE question -> ONE more try
                |        |                             |
                |        +--------> (4) ESCALATE <-----+
                |                    hand-off packet -> L2/L3
                |                              |
                |                    L2/L3 fixes it, writes what fixed it
                v                              v
        (5) LEARN: quality check ("is this note good enough?")
              |                     |
        good enough            not good enough
              |                     |
     added to the library     waits for a person:
     (searchable at once)     Approve / Reject
```

**Why it is built this way.** Each box exists because a real support desk needs it. "Known vs novel"
stops the app from confidently guessing. "Never repeat a failed step" stops the annoying loop of "have you
tried turning it off and on again?" for the third time. The learning box means today's fix helps tomorrow's
engineer.

---

## 5. What happens when you click Analyze

Here is the whole pipeline in order, with the reason for each step.
(Code lives in `backend/services/analysis.py`, `backend/retrieval/`, `backend/intelligence/`, `backend/rag/`.)

```
 your text
    |
    v
 5.1 UNDERSTAND   "restarting fixes it temporarily" + slow + freeze  ->  memory leak
    |
    v
 5.2 SEARCH        by meaning (ChromaDB)  +  by keywords (BM25)  ->  merge (RRF)
    |
    v
 5.3 RE-RANK       a second, sharper model re-orders the best 30 -> relevance %
    |
    v
 5.4 FINGERPRINT   component / symptom / trigger / scope ...
    |
    v
 5.5 FAMILY        which of the 30 families is closest?
    |
    v
 5.6 KNOWN or NOVEL?   four signals -> P(known) vs cut-off 0.4896
    |          \
    |           novel -> stop. No fix is forced.
    v
 5.7 PICK ONE FIX  group past fixes by strategy, score them, compute confidence
    |
    v
 5.8 SAFETY CHECK  destructive? disruptive? enough sources?
    |
    v
 5.9 EXPLAIN       evidence chain  +  5.10 GRADE THE QUERY (Good / Fair / Poor)
```

### 5.1 Understand (vague to technical)
- **What:** A rule list turns everyday words into technical ideas. "takes forever" becomes *performance
  degradation*. "Slow **and** freezes **and** restart fixes it" becomes *memory leak, resource exhaustion*.
  It also spots hints: environment (production?), scope (one user or everyone?), trigger (after a
  deployment?), component (database? VPN?).
- **Why:** People do not write like log files. Searching "feels slow" would miss a ticket that says "heap
  exhausted". Translating first finds more true matches.
- **The AI is optional here.** It is only asked for extra search terms if the rules found fewer than 2, and
  those terms are tagged *inferred*.
- **Also decided here: is the report "vague"?** A report is vague if it has 9 or fewer meaningful words,
  or a low "specificity" score (below 0.4). This matters later for clarifying questions.

### 5.2 Search: two searches merged
- **What:** One search finds incidents that *mean* the same thing (semantic, ChromaDB). Another finds
  incidents that *contain the same words* (BM25). Each returns 50 candidates. They are merged with
  **Reciprocal Rank Fusion** (RRF, k = 60): an incident that ranks high in *both* lists wins.
- **Why:** Meaning-search is good with paraphrases but can miss exact codes like "ZX-99". Keyword search
  is the opposite. Their scores are on different scales, so RRF merges by *rank* instead of by score.
  It also still works if one of the two searches breaks (see [Section 11](#11-safety-nets)).
- **Copies are collapsed.** If 22 tickets are word-for-word identical, they count as **one** piece of
  evidence (with a note "22 collapsed"). Otherwise one repeated ticket would look like a crowd.
- **Filters** (priority, impact, category, and so on) are available through the API.

### 5.3 Re-rank
- **What:** A "cross-encoder" model reads your text and each candidate *together* and re-orders the best
  30. Its raw score is converted (a maths step called Platt calibration) into a **percentage: "how likely is
  this incident truly relevant?"**
- **Why:** The first search is fast but rough. The second read is slower but much better at telling a
  true match from a near-miss. The percentage is what you see as *relevance*.

### 5.4 Fingerprint
- **What:** Ten fields, each with a source tag and the evidence phrase it came from. Anything the text does
  not say stays `Unknown`. A brand-new incident's **root cause is always Unknown**; it is *inferred* later
  from similar past incidents, never invented.
- **Why:** The fingerprint is reused everywhere: family matching, clarifying questions, correlation, the
  evidence chain.

### 5.5 Family match
- **What:** The app checks which of the 30 families your incident is closest to, using the retrieved
  incidents' family votes and closeness to each family's "centre". The result is a **match strength** from
  0 to 1.
- **Why:** A family answers "what *kind* of problem is this?", which is more useful than one lookalike ticket.

### 5.6 Known or novel?
- **What:** Four real signals are blended by a small model into **P(known)**:
  1. the best re-ranker score,
  2. the best meaning-similarity,
  3. how close the incident is to a family centre,
  4. how many of that family's members share your symptom.

  If P(known) is **below 0.4896 -> Novel**. That cut-off was chosen on test data with this rule: *catch as
  many truly-new incidents as possible while wrongly calling a known one "novel" no more than 2% of the
  time.* It is not a number someone picked by feel.
- **Why:** The most dangerous behaviour of a search tool is a confident answer to a question it has never
  seen. This step lets the app say "I don't have a playbook for this."
- **If the search is degraded** (re-ranker or vector store down), the verdict becomes **Undetermined**
  (the model was trained with all four signals, so judging with fewer would be unfair).

### 5.7 The confidence number (worked example)
The top fix comes from grouping the retrieved incidents by *strategy* and scoring each group. Then:

```
   confidence  =  best relevance   x   agreement   x   provenance factor

   Real example I observed ("Memory leak" preset), fix: "Restarting the application service"

        0.9612            x     0.5856      x        0.8         =   0.4503
   (the best match is        (58.6% of the        (the evidence is
    96% relevant)             evidence backs        AI-written, so it
                              this strategy)        counts x0.8)
```

- **Agreement** = this strategy's share of all the evidence. Competing fixes lower it.
- **Provenance factor** = 1.0 for original text, 0.8 for synthetic. Because ~95% of the library is
  synthetic, **the confidence can almost never exceed 0.80**. That is deliberate honesty.
- **Evidence weight** of each incident = relevance x its **quality score** (see [Section 9](#9-how-the-app-learns)).
  Poor notes like "closed" or "fixed" are **skipped entirely**.
- **After a family match** (strength 0.5 or more), that family's own strategies get a boost of
  (1 + match strength). This is why, after a failed step, the *next* suggestion is another way of fixing
  the *same* problem, not something from an unrelated family.
- **Never guessed by an AI.** If results were not re-ranked, confidence is shown as **"undetermined"**.

### 5.8 Safety check
- **Destructive** words (delete, drop table, truncate, wipe, reimage, restore from backup, kill session ...):
  recommended **only with 2 or more independent past sources**, and always marked "requires human
  confirmation and a verified backup". With fewer sources the step goes into a "blocked by guardrails" list and
  the next safe strategy is used.
- **Disruptive** words (restart, reboot, recycle, failover, rollback ...): allowed, but marked "confirm with
  the service owner / do it in an agreed window".
- **No history behind it** = flagged unsupported.
- **Observed:** "Restarting the application service" -> `disruptive=True`, `requires_human_confirmation=True`.
  "Reinstalling the correct printer driver" -> neither.

### 5.9 Evidence chain ("Why did the system recommend this?")
A fold-out panel listing: the report as understood, the fingerprint, the family matched, an **evidence
strength** score computed from real numbers, the historical incidents used, root-cause evidence, resolution
evidence, and, kept *separate*, anything an AI added. For a novel incident, the family, root cause and
resolution are marked **"insufficient evidence"**. Nothing is fabricated.

### 5.10 Grade the query: Good / Fair / Poor
The **Query evaluation** line is the plain average of four signals, each between 0 and 1:

```
   score = average( retrieval relevance,  P(known),  family match strength,  fix confidence )

   Good  = 0.70 or more        Fair = 0.40 to 0.70        Poor = below 0.40
   Any NOVEL verdict is always Poor (so the grade never contradicts the red bar).
   A signal that cannot be computed is left OUT of the average, not counted as zero.
```

Real example (Memory leak): (0.985 + 0.998 + 0.932 + 0.450) / 4 = **0.841 -> Good**.
The Good and Fair cut-offs are *display bands*, not fitted numbers, and the app says so on screen.

---

## 6. Screen-by-screen tour

The left menu has three groups: **Operate** (Assistant, Troubleshooting, Escalations, Novel incidents),
**Understand** (Patterns, Knowledge base), **Improve** (Feedback, Evaluation). A number next to
*Escalations* is how many are waiting. Under the menu: system status, a "Decision support only" reminder,
and a light/dark theme switch.

```
 +----------------+----------------------------------------------------------+
 | Incident       |                                                          |
 | Intelligence   |   (the page you are on)                                  |
 |                |                                                          |
 | OPERATE        |                                                          |
 |  Assistant     |                                                          |
 |  Troubleshoot. |                                                          |
 |  Escalations 1 |                                                          |
 |  Novel incid.  |                                                          |
 | UNDERSTAND     |                                                          |
 |  Patterns      |                                                          |
 |  Knowledge base|                                                          |
 | IMPROVE        |                                                          |
 |  Feedback      |                                                          |
 |  Evaluation    |                                                          |
 | [status light] |                                                          |
 | [theme toggle] |                                                          |
 +----------------+----------------------------------------------------------+
```

### 6.1 Assistant: "What is this, and what do I try first?"
**Purpose:** the main screen. One report in, one verdict and one first step out.

**How to use it**
1. Type a report, or click a **preset**: *Memory leak, Vague report, Login loop, Report timeouts, Printer
   queue, Tape robot (unseen)*.
2. Click **Analyze** (or press **Ctrl + Enter**). The button stays disabled until you type **more than 3
   characters**.
3. Read from top to bottom:

```
 +--------------------------------------------------------------------------+
 | KNOWN PATTERN (blue)   Memory leak / heap exhaustion       P(known) 0.998 |
 |  Family F001 ... match strength 0.985           above threshold 0.490    |
 +--------------------------------------------------------------------------+
 | Query evaluation:  GOOD  0.841        [Details]                          |
 +--------------------------------------------------------------------------+
 | FIRST STEP:  Restarting the application service                          |
 |   Confidence 0.45 = 0.96 x 0.59 x 0.80     ! Needs human confirmation    |
 |   Backed by 5 past incidents (links)      Expected: "memory back to 40%" |
 |   [ Start guided troubleshooting ]                                       |
 +--------------------------------------------------------------------------+
 | Other strategies (the Strategy panel: reopen rate, median time...)       |
 | How the report was read | What the system extracted | Pattern family     |
 | Likely root cause | Why did the system recommend this? (evidence chain)  |
 +--------------------------------------------------------------------------+
```

- **Blue bar** = known. **Red bar** = novel. **Dark bar** = undetermined.
- If there is no evidence-backed fix, you see **"No evidence-backed resolution found"**.
- The **Strategy panel** shows the *competing* historical fixes side by side, with real reopen statistics
  (only shown when at least 20 real outcomes exist; otherwise it says the stats are not supported).
  **One ranked fix leads; the alternatives are there if you want them.**
- Every ID (like `IM0006370` or `F001`) is a **link** to that incident or family.
- Each analysis gets its own ID like `NEW-20260929...-7666`. Click it for the full record.
- **Why the bar is a whole block of colour:** it is the first thing you read. Verdict first, details after.

### 6.2 Guided Troubleshooting: "Walk me through it"
**Purpose:** one step at a time, with a record of every try.

**How to use it:** from the Assistant click **Start guided troubleshooting**, or open this page, type a
report and click **Start troubleshooting**.

```
   ROUND 1 of 3:  have you tried this?
   +--------------------------------------------------------+
   |  Restarting the application service        conf 0.45    |
   +--------------------------------------------------------+
   Notes (optional): [ memory back to 40% for ten minutes   ]
   [ It worked ]  [ It failed ]  [ Not sure ]  [ Escalate now ]

   Will not be suggested again:   ~~Restarting the application service~~
```

- **It failed:** the step (and any near-identical step) is crossed out and never offered again. The next
  best step appears.
- **Not sure:** the step is skipped for the *next* pick only (not banned for ever).
- **It worked:** the incident is marked **Resolved**. Two buttons appear: **Generate postmortem and update
  the knowledge base**, and **Rate this session**.
- **Escalate now:** hands off immediately.
- Below: **Attempt log**, **Clarifications**, **Session timeline and agent messages**.

The full rules are in [Section 7](#7-guided-troubleshooting-the-rules).

### 6.3 Escalations: "The senior engineer's side"
**Purpose:** the L2/L3 engineer's inbox. *(Added on request. The original brief only asked for the packet.)*

1. Pick an item from **Open** (left list).
2. Read the right side: the problem, why it was escalated, likely root cause, suggested next step, and
   **what was already tried** (crossed out so nobody repeats it). The **Full escalation packet** is at the
   bottom, plus a **Raw packet** view.
3. When fixed, write **What fixed it?** (at least **10 characters**), add the **root cause** if known, and
   click **Mark resolved**.
4. The item moves to **Resolved**. The fix goes through the same quality check as any other and the page
   tells you: **added to the knowledge base** or **waiting for approval**.

You cannot resolve the same escalation twice.

### 6.4 Novel incidents: "Is this actually new?"
Presets: *GPS time server, HR portal login loop, Tape library arm*. Click **Check novelty**. You get the
verdict bar, P(known) next to the cut-off, and the nearest past incidents.
**Why it exists:** it lets you see the "known vs novel" decision on its own, without the rest of the analysis.

### 6.5 Patterns: "What keeps happening?"
- A plain list of the **30 families**. Open one (for example `F001`) to see:
  **Signature** (share of members per fingerprint value), **Causal chain**
  (trigger -> failure -> symptom -> impact -> fix -> outcome), **Recurrence** (real timestamps),
  **Strategies** (the competing fixes), **Members** (a sample).
- Framed as **"Potential pattern requiring investigation"**, on purpose. A pattern is a lead, not a verdict.
- **Causal chain links come in three kinds and must never look alike:**
  **observed** (solid line: backed by real records), **derived** (dashed: from a fixed rule),
  **inferred** (dotted: a best guess).
- An unknown family, e.g. `/patterns/NOPE`, gives a "not found" page (the API returns 404).

### 6.6 Knowledge base: "What is waiting for a person?"
- **Recently added:** incidents that passed the quality check and joined the library.
- **Manual review:** fixes that scored too low. Click **Approve** or **Reject**.
- **Process resolved incidents:** a manual button for the nightly batch. With nothing pending it says
  "Processed 0 pending resolved incidents."

### 6.7 Feedback: "Was the advice any good?"
- Choose **Helpful / Not helpful / Skip**.
- Optional reasons: *wrong incident, wrong resolution, incomplete, outdated, escalation required, other*.
- Four questions (Yes / No / Not sure): *Was the root cause right? Was the pattern family right? Did
  troubleshooting resolve it? Was escalation appropriate?*
- The **Incident ID is required** and is prefilled from your last analysis or session.
- **What it really does:** it lowers the quality score of the past incidents that misled the app (by 0.15
  each) and may add your resolved incident to the library. **No AI model is retrained.** The page says so.

### 6.8 Evaluation: "Was that a good question?"
Type a query or click a preset: **Relevant, Vague, Unseen incident, Unrelated, Gibberish**. Click **Evaluate**.
You get the grade, score and the four signals, plus the **nearest historical incidents** as proof. Every query
you analyse in the Assistant is also listed under **Evaluated queries**.
*(The whole-app report card is not shown in this website any more; see [Section 14](#14-the-report-card-numbers-in-plain-english).)*

### 6.9 Incident record page (click any ID)
Shows **Recorded fields** (each with its provenance tag), **Fingerprint**, **Pattern family**, **Causal
chain** (or "No causal chain for this record" if there are no timestamps), and **Resolution attempts**.

### 6.10 Live Correlation: not in the new website
The new Next.js site has **no Live Correlation page**. It exists in two places:
- the **older Streamlit app** (`streamlit run frontend/app.py`, "Live Incident Correlation" page), and
- the **API**: `POST /incidents/simulate` and `GET /incidents/correlations` (try them in Swagger at
  <http://localhost:8000/docs>).

See [Section 10](#10-live-correlation).

---

## 7. Guided troubleshooting: the rules

```
                    START  (analyze the report)
                      |
          +-----------+------------------+
          |                              |
       NOVEL?                        low confidence AND vague,
          |                          or two families nearly tied?
      status "novel"                       |
      -> fresh investigation      ASK ONE QUESTION  (max 1 per session)
      -> escalation packet                 |
                                           v
                  +------------------> SUGGEST STEP (round n of 3)
                  |                        |
                  |        +---------------+------------------+
                  |        |               |                  |
                  |     WORKED          FAILED            NOT SURE
                  |        |               |                  |
                  |     RESOLVED     exclude this        skip it once
                  |     -> postmortem  strategy AND        (not banned)
                  |     -> KB update   near-identical            |
                  |                    steps                     |
                  |                        \_____________________/
                  |                                  |
                  |                       round 3 reached, or no
                  |                       evidence-backed step left?
                  |                          |               |
                  |                         no              yes
                  |                          |               |
                  +-------- next-best step --+   PRE-ESCALATION CHECK:
                                                  is one useful field missing?
                                                    |             |
                                                   yes            no
                                                    |             |
                                        ask ONE question       ESCALATE
                                        (answer -> ONE bonus       ^
                                         step; if it fails  -------+
                                         -> ESCALATE)
```

**The rules, and why each exists**

| Rule | Plain meaning | Why |
|---|---|---|
| **Round cap = 3** | At most 3 suggested steps before the pre-escalation check. | The app shouldn't string an engineer along forever. |
| **A failed step is banned** | Also banned: steps whose wording is very close (similarity 0.5 or more, e.g. two phrasings of "restart the service"). | Different words, same action. Suggesting it again is useless. |
| **"Not sure" is a soft skip** | Skipped once, can return later. | "Unknown" is not "failed". |
| **At most 1 question per session** | Never a quiz. | Questions cost the engineer time. |
| **3 reasons to ask** | (1) low confidence (below 0.45) **and** vague report; (2) top two families within 0.08 of each other and a field that would separate them is unknown; (3) about to escalate and a useful field is missing. | Ask only when the answer can change what happens. |
| **Never ask what is already known** | Skips fields the text or an earlier answer covers. | Don't ask twice. |
| **Question order** | Vague: component, then scope, then trigger, then environment. Pre-escalation: trigger, scope, environment, component. | Most useful first. |
| **No step invented** | If nothing evidence-backed remains, it escalates. | No evidence, no advice. |
| **The next step comes from search, not from "step 2 usually follows step 1"** | The data has no record of step sequences, so none is claimed. | Honesty about the data. |

**Real trace** (from the recorded checkpoint `docs/checkpoints/phase6_troubleshooting_trace.json`):

| Round | Suggested step | Confidence | Answer |
|---|---|---|---|
| 1 | Restarting the application service | 0.4345 | FAILED |
| 2 | We deployed the supplier's hotfix | 0.3664 | FAILED |
| 3 | The vendor provided a patch ... stable over 48 hours | 0.717 | FAILED |
| - | Question: "Did this start after a recent deployment or configuration change?" | - | "yes, after a deployment / release" |
| - | Nothing new found -> **escalated to L2** | - | - |

---

## 8. Escalation: handing the problem to a senior engineer

**When it happens:** you click *Escalate now*, the round cap is hit, no evidence-backed step is left, or the
incident is novel.

**What the packet contains** (nothing missing, so L2 does not have to ask again):
incident summary and symptoms, the fingerprint, **checks performed**, the **full attempt history**,
**"failed approaches: do not repeat"**, top retrieved past incidents, **likely root cause** (with "likely /
possible / weakly supported" depending on how many retrieved incidents agree: 60% or more = likely, 30% or
more = possible), **suggested team and expertise**, **tier with reasons**, the **recommended next diagnostic
action**, and any clarification asked and what was learned.

**How the tier is chosen.** Start at the first tier (L1). Each reason below moves it up **one** level (capped
at the top tier):

| Reason | Adds one level when... |
|---|---|
| Priority | priority is 1 or 2 |
| Novel | the incident is novel |
| Destructive | the recommended action is destructive |
| Exhausted | guided troubleshooting failed to the cap |
| History: reassignments | this family needed 2.0 or more reassignments on average |
| History: reopens | family reopen rate is 15% or more **and** troubleshooting was exhausted |

If no rule applies the reason reads "no escalation criteria met: first line". (Observed: the Memory leak
triage came out **L1**; the recorded 3-fails trace came out **L2**.)

**Which team.** From the fingerprint's *component* (Database -> Database Administration, VPN gateway ->
Network Operations, SAP -> SAP Competence Center, and so on). If unknown, it falls back to the CI group, then
the category, then **Service Desk**. **No individual is ever named**, because the data has no assignee.

**If no untried historical step remains**, the "next action" is labelled **"system guidance (not from
historical evidence)"**: collect logs, metrics and a timeline. It is never disguised as history.

---

## 9. How the app learns

```
   resolved incident
        |
        v
   build a candidate record:  fix that WORKED + your notes + failed attempts
                              + postmortem root cause + feedback
        |
        v
   QUALITY CHECK  (score 0 to 1)
        |
   +----+----------------------------+
   |                                 |
 score >= 0.55                    score < 0.55
   |                                 |
 fingerprint -> join/create        MANUAL REVIEW queue
 a family -> embed -> add to       (never silently added,
 search index -> rebuild keyword   never silently thrown away)
 index -> searchable NOW               |
                                  Approve -> indexed   Reject -> dropped
```

**How the quality score works** (`backend/knowledge/quality.py`)
- A note is scored on **detail** (length, a concrete action word, a cause, a verification), **completeness**,
  **consistency** (does the fix resemble how similar incidents were fixed?), and **outcome**
  (reopened or heavily reassigned tickets score lower).
- Generic notes such as *"closed", "fixed", "ok", "restarted"* score about **0.05**.
- Tiers: **high** at 0.70 or more, **medium** at 0.50 or more, otherwise **low**.
- A confirmed working fix counts as real outcome evidence. **Feedback:** helpful **and** root-cause-correct
  gives +0.05; not helpful or wrong root cause gives -0.15.
- The library's own health (Observed): 3,130 records, tiers high 2,624 / medium 327 / low 179; flags include
  343 generic notes, 143 exact duplicates, 394 near duplicates, 107 category-vs-text conflicts.

**Why a quality gate?** Without it, one careless "fixed" would enter the library and mislead the next
engineer. A gate that *asks a person* (instead of silently deleting) keeps every decision visible.
Each stage is written to an audit table (`kb_evolution_events`).

**Ways an incident can enter:** answering *It worked* then Postmortem or Feedback; an L2/L3 resolving an
escalation; the **Process resolved incidents** button; the optional nightly worker
(`python scripts/kb_evolution_batch.py --loop`).

---

## 10. Live correlation

**The idea.** Three people report three different-sounding problems within a few minutes. The tickets are
really **one** outage. The app spots that and raises **"Possible single ongoing incident."**

**The rules** (`backend/intelligence/correlation.py`)
- **Window: 30 minutes.** Older tickets are ignored.
- **Alert at 2 or more linked tickets.**
- Two tickets are **linked** if their text is very similar (meaning-similarity 0.90 or more, a value picked
  by testing on simulated streams) **or** both match the **same family** (match strength 0.3 or more, and
  not flagged novel).
- Linking is **chained**: A links B and B links C means one group.
- The alert is always framed **"possible correlation: confirm before merging tickets"**.

**Real results (Observed, via `POST /incidents/simulate`)**

| Preset | Tickets and minutes | Result |
|---|---|---|
| `db-outage-burst` | 3 database-slowness tickets at 0, 4, 9 min | 1 alert, **2** tickets (family F005, shared symptom "timeout"), detected after **240 s**. The 3rd ticket matched a *different* family (F004) and wasn't 90% similar, so it wasn't joined. |
| `vpn-storm` | 3 VPN tickets at 0, 3, 6 min | 1 alert, **3** tickets (F022, shared component "VPN gateway"), **180 s** |
| `memory-leak` | 3 slow/freezing tickets at 0, 5, 12 min | 1 alert, **3** tickets (F001), **300 s** |
| `unrelated-noise` | printer, account lockout, SAP dump | **0 alerts** (correct) |
| custom: payroll batch + coffee machine, 3 min apart | unrelated | **0 alerts** |
| custom: two VPN tickets **45 min** apart | related but outside the 30-min window | **0 alerts** |

The `db-outage-burst` result is a good lesson: the rules are honest, not magic. The report card (Section 14)
says the same thing: **every simulated burst was caught, but about 22% of alerts were false alarms.**

---

## 11. Safety nets

The app is built to **degrade honestly**: if a part breaks, it keeps working and **labels** the weaker answer.

| # | What breaks | What the app does | What you see |
|---|---|---|---|
| 1 | No AI key / AI unreachable | **Retrieval-only mode.** Ranked results, fingerprint, family, verdict, evidence chain, extractive fix. No AI text. | Band: "Retrieval-only mode: LLM unavailable" |
| 2 | Cloud embeddings fail | Falls back to the local embedding model and logs it. If the index was built with another model, meaning-search is turned off rather than mixing incompatible number spaces. | `/health` shows the fallback reason |
| 3 | Re-ranker fails | Results keep merged order, **no confidence is shown** (it would be invented), verdict is "undetermined". | Label "unreranked" |
| 4 | No good match at all | **NOVEL INCIDENT**. No fix is forced. Evidence chain says "insufficient evidence". | Red bar |
| 5 | Top fix reported FAILED | Recorded, banned, next best chosen. | Crossed-out step |
| 6 | Vector database down | Keyword-only search; re-checked every 30 s. Novelty becomes "undetermined". | "keyword-only (semantic search unavailable)" |
| 7 | Vague report | Not an error. One clarifying question. | Question card |
| 8 | Website cannot reach the engine | Every page shows an error state with retry. | "Could not load this view." |

**Other guards:** destructive-action rule ([5.8](#58-safety-check)); an AI-written step with no support in a
cited note is flagged "unsupported" and kept apart from history; an uncalibrated model never invents a
number (verdict stays "undetermined"). Full table: `docs/FALLBACKS.md`.

---

## 12. Test cases you can run by hand

**How to read the tables.** *Status*: **Obs** = I ran it and saw this; **Code** = expected from source code
or automated tests, not clicked by me. "Why" explains the behaviour. Use the preset buttons in the website
for the query texts.

> Numbers can drift slightly (for example the memory-leak confidence was 0.4345 in an earlier recorded run and
> 0.4503 when I ran it) because the library grows as incidents are added. **Compare the verdict, the grade and
> the rough size of the numbers, not the fourth decimal.**

### 12.1 Assistant

| ID | Steps | Expected result | Status | Why |
|---|---|---|---|---|
| A1 | Preset **Memory leak** -> Analyze | **Known pattern** (blue), P(known) about 0.998. Family **F001**, memory leak / heap exhaustion (match about 0.98). First step **"Restarting the application service"**, confidence about 0.45 = 0.96 x 0.59 x 0.80. Marked *needs human confirmation*. Grade **Good** 0.84. | Obs | Slow + freeze + "restart fixes it" is translated to *memory leak* before search. Restart is a "disruptive" word. |
| A2 | Preset **Vague report** -> Analyze | Known-ish, grade **Fair** 0.60. Fix confidence only about **0.30**. Tip: "Vague wording: add the component, the symptom and the trigger". | Obs | Few details = weaker evidence agreement. Confidence 0.30 is below the 0.45 level that triggers a clarifying question in Troubleshooting. |
| A3 | Preset **Login loop** | **Known**. Family **F007** (authentication: SSO / directory sync failure), match about 0.63, relevance 0.95, **Good** 0.78, P(known) about 0.90. | Obs | Clear symptom, and history has it. |
| A4 | Preset **Report timeouts** | **Known**, **Good** 0.79, fix confidence about 0.43. | Obs | Timeouts at peak time match the database / connection families. |
| A5 | Preset **Printer queue** | **Known**, **Good** 0.92. Fix **"Reinstalling the correct printer driver"**, confidence about **0.71**, backed by 9 incidents. **No** confirmation warning. | Obs | Strong agreement (91%) among many similar past incidents. Reinstalling a driver is not a "disruptive" word. |
| A6 | Preset **Tape robot (unseen)** | **Novel incident** (red). P(known) about **0.006** vs cut-off 0.4896. **No fix.** "No evidence-backed resolution found." Grade **Poor** 0.01. | Obs | Nothing in the library resembles a tape library. The nearest family only matches at about 0.016 and is "below the threshold, so it is not used as evidence". |
| A7 | Type `abc` (3 characters) | **Analyze is disabled.** Type 4+ characters and it enables. | Code | The box needs more than 3 characters. |
| A8 | Press **Ctrl + Enter** with a valid report | Runs the analysis | Code | Keyboard shortcut. |
| A9 | Click any incident ID in the result | Opens that incident's record page | Code | Every ID is a link. |
| A10 | Open **Why did the system recommend this?** | 7 blocks: understood as, fingerprint, family, evidence strength, historical incidents, root cause evidence, resolution evidence, plus a separate "LLM inference" block | Code | The evidence trail. Strength values are numbers between 0 and 1, or "insufficient evidence". |
| A11 | Click **Start guided troubleshooting** | Moves to Troubleshooting with the same report | Code | Hand-over from analysis. |
| A12 | Analyze the same report twice | Same verdict. A **new** analysis ID each time. | Code | Each run is a separate record. |

### 12.2 Novel incidents

| ID | Steps | Expected | Status | Why |
|---|---|---|---|---|
| N1 | Preset **GPS time server** -> Check novelty | **Novel**, P(known) about **0.0135** | Obs | Not in the library. |
| N2 | Preset **HR portal login loop** | **Known** (login family) | Code (its twin "Login loop" was Obs: 0.903) | Close to the SSO family. |
| N3 | Preset **Tape library arm** | **Novel**, about 0.006 | Obs | As A6. |
| N4 | Enter `What is the best pizza recipe for a birthday party?` | **Novel**, P(known) about 0.0002 | Obs | Not an IT incident at all, so no similarity. (The app has no separate "not IT" label: it just finds no history.) |
| N5 | Enter `asdf qwerty zxcv` | **Novel**, about 0.0005 | Obs | Nonsense matches nothing. |
| N6 | Turn the re-ranker off (see 12.10) and check novelty | **Undetermined**, not a guess | Code | Model needs all four signals. |

### 12.3 Query evaluation

| ID | Query (preset) | Grade / score | The four signals (relevance / P(known) / pattern / fix) | Status |
|---|---|---|---|---|
| E1 | **Relevant** (memory leak) | **Good 0.841** | 0.985 / 0.998 / 0.932 / 0.450 | Obs |
| E2 | **Vague** | **Fair 0.600** | 0.739 / 0.742 / 0.620 / 0.301 | Obs |
| E3 | **Unseen incident** (tape robot) | **Poor 0.010** | 0.023 / 0.006 / 0.010 / 0.000 | Obs |
| E4 | **Unrelated** (pizza) | **Poor 0.008** | 0.020 / 0.000 / 0.012 / 0.000 | Obs |
| E5 | **Gibberish** | **Poor 0.009** | 0.024 / 0.000 / 0.010 / 0.000 | Obs |
| E6 | `GPS time server ...` | **Poor 0.032** (novel, so always Poor) | 0.064 / 0.014 / 0.050 / 0.000 | Obs |
| E7 | `printer broken` (2 words) | **Good 0.896** *and* a tip: "Very short query: name the affected component, the symptom and when it happens." | 0.928 / 0.984 / 0.928 / 0.742 | Obs |
| E8 | Empty text (API) | HTTP **422** error | Obs | The request needs at least 1 character. |

**Two lessons from E7 and E5.** A short query can still grade **Good** if it clearly matches a family, but
the app still nudges you to add detail. Gibberish and unrelated text get **Poor** *plus* the note "No IT
symptom, component or trigger was recognised".

### 12.4 Guided troubleshooting

| ID | Steps | Expected | Status | Why |
|---|---|---|---|---|
| T1 | Start with the Memory leak text | Round 1 shows a step and buttons | Code (and recorded trace) | Top-ranked strategy. |
| T2 | Answer **It failed** on round 1 | Step crossed out under "Will not be suggested again". A **different** step appears (round 2). | Code + trace | Failed strategy excluded. |
| T3 | Fail every step | Never the same strategy twice. After round 3 **one** question ("Did this start after a recent deployment...?"), then escalation with tier **L2** and every attempt in the packet. | Code + trace | Round cap plus pre-escalation clarification. |
| T4 | At that question click **Decline** | Escalates straight away | Code | "Clarification declined" means no new information. |
| T5 | Answer that question helpfully | One bonus step. If it fails, or nothing new is found, it escalates. | Code | One extra try at most. |
| T6 | Answer **It worked** | Status **Resolved**. Buttons for postmortem and rating. | Code | Loop closes. |
| T7 | Answer **Not sure** | Step skipped once; next-best is offered | Code | Soft skip. |
| T8 | Start with `the system is slow` | A clarifying question first: **"Is this affecting a single user or multiple users?"** (match confidence 0.33, below 0.45, and the report is vague) | Recorded (checkpoint) | Low confidence + vague. |
| T9 | Start with the tape-robot text | Status **novel**: "No historical playbook". Escalation packet available. | Code | No fix forced. |
| T10 | Click **Escalate now** on round 1 | Escalated at once, packet built | Code | Manual hand-off. |
| T11 | Answer the same step twice (API) | Error 400: "already answered" | Code (unit test) | A response is recorded once. |
| T12 | Send response `MAYBE` (API) | **422** | Obs | Only WORKED / FAILED / UNKNOWN allowed. |
| T13 | Respond with no session (API) | **404** | Obs | Nothing to respond to. |
| T14 | Start with no text (API) | **400** | Obs | `text` is required to start. |
| T15 | Answer a clarification with `only me` / `it's in prod` / `no` | Understood as *single user* / *Production* / *no recent change* | Code (unit test) | Free text is mapped to a fingerprint value. |

### 12.5 Escalations

| ID | Steps | Expected | Status | Why |
|---|---|---|---|---|
| X1 | After T3, open **Escalations** | An **Open** item, the menu count goes up by 1, packet shows failed steps crossed out | Code | Escalation record saved. |
| X2 | Try to resolve with the note `ok` | Rejected (**422**, note under 10 characters) | Obs | Forces a real note. |
| X3 | Resolve a missing escalation (API, ID 999999) | **404** | Obs | Not found. |
| X4 | Write a real note and root cause, **Mark resolved** | Moves to **Resolved**. Resolved by "L2..." (matches the tier). Message: added to the library **or** waiting for approval. The incident status becomes **Resolved**. | Code (integration test) | Goes through the normal quality gate. |
| X5 | Try to resolve it a second time | Error (400) | Code | Already closed. |
| X6 | Reopen the original troubleshooting session | Status still **escalated**, with the resolution shown | Code | It records what happened, then how it ended. |
| X7 | Nothing escalated yet | Empty state: "Nothing has been escalated" | Code | When I checked: 1 escalation in total, 0 open. |

### 12.6 Knowledge base

| ID | Steps | Expected | Status | Why |
|---|---|---|---|---|
| K1 | After a WORKED session + rated helpful with all answers Yes | Appears in **Recently added** and is searchable | Code (integration test) | Good note, passes the gate. |
| K2 | Resolve an incident with the note `ok` and process it | Goes to **Manual review** | Code (integration test) | Generic note scores far below 0.55. |
| K3 | Click **Reject** on it | Status **rejected**, not indexed | Code | A person said no. |
| K4 | Click **Approve** | Indexed and searchable | Code | Approval overrides the gate, and it is logged. |
| K5 | Click **Process resolved incidents** with nothing pending | "Processed 0 pending resolved incidents." | Code | Nothing to do. |
| K6 | Search for a phrase from a newly added fix | It comes back in the results | Code (integration test) | The keyword index is rebuilt after each addition. |

### 12.7 Feedback

| ID | Steps | Expected | Status |
|---|---|---|---|
| F1 | Leave Incident ID empty | Cannot submit (ID is required) | Code |
| F2 | Not helpful (or reason *wrong resolution / outdated / wrong incident*) on an analysis | "Feedback recorded". Each past incident that backed the recommendation loses 0.15 quality and is listed under "penalised". Logged as an audit event. This only happens when the page knows which incidents backed it (it is prefilled after an analysis or a session). | Code |
| F3 | Helpful + root cause Yes on a *resolved* live incident | Recorded. The fix goes through the quality check and may be added to the library (+0.05 quality bonus). Feedback on an unresolved incident is only stored. | Code |
| F4 | Submit for an ID that does not exist | Still shows "Feedback recorded": the API saves the rating without checking the ID. Nothing else happens (no penalty, no library update). | Code |
| F5 | Submit while the engine is off | "Feedback was not recorded" | Code |

**Why penalise?** If a recommendation was wrong, the past notes that led to it should count for *less*
next time. This changes records only; **nothing is retrained**.

### 12.8 Patterns and records

| ID | Steps | Expected | Status |
|---|---|---|---|
| P1 | Open **Patterns** | **30** families. First is `F001`, memory leak / heap exhaustion. | Obs |
| P2 | Open `F001` | Signature, causal chain, recurrence, strategies, members. Header: "Potential pattern requiring investigation". | Code |
| P3 | Open `/patterns/NOPE` | Not-found page (API **404**) | Obs |
| P4 | Open `/incidents/IM-does-not-exist` | Not-found (API **404**) | Obs |
| P5 | Open an old (`IM...`) record | Fields with provenance tags. Text fields show **synthetic** in amber. | Code |
| P6 | Open a record with no timestamps (a text-rich `INC-...` one) | "No causal chain for this record" | Code |

### 12.9 Live correlation (API / Streamlit)

See the six observed cases in [Section 10](#10-live-correlation): three real bursts, one noise set, one
unrelated pair, one too-far-apart pair.

| ID | Extra checks | Expected | Status |
|---|---|---|---|
| C1 | `GET /incidents/correlations` after a preset | Shows window 30 min, min 2, threshold 0.9, the events and alerts | Code |
| C2 | Simulate with `reset: true` | Old events and alerts are cleared first | Code |
| C3 | Send tickets 45 minutes apart | No alert (outside window) | Obs |

### 12.10 System and failure tests

| ID | How | Expected | Status |
|---|---|---|---|
| S1 | Stop Terminal 1 (the engine) and refresh the website | "Could not load this view." on every page; status light shows down | Code |
| S2 | Remove the AI key (or set `LLM_PROVIDER=none`) and restart the engine | Band "Retrieval-only mode: LLM unavailable"; no "LLM synthesis" panel; fix is copied word-for-word from a past note | Code (test) |
| S3 | Set `EMBEDDING_PROVIDER=openai` with no key | App starts, uses local embeddings, `/health` shows the fallback reason | Code (test) |
| S4 | Set `RERANKER_PROVIDER=none` | Label "unreranked"; **no confidence numbers**; novelty "undetermined" | Code (test) |
| S5 | Break/stop the vector database | Label "keyword-only (semantic search unavailable)"; results still appear | Code (test) |
| S6 | Set `ESCALATION_TIERS=L2,L3` | Tiers use that order | Code |
| S7 | Narrow the browser below 1200 px | Page scrolls sideways (no phone layout, by design) | Code |

### 12.11 API edge cases

| ID | Request | Result | Status |
|---|---|---|---|
| I1 | `GET /health` | 200, `status: ok` | Obs |
| I2 | `POST /incidents/search` with `top_k` 500 | **422** (limit is 1 to 50) | Obs |
| I3 | `POST /incidents/troubleshoot` `{action: "respond"}` with no session | **404** | Obs |
| I4 | `POST /incidents/triage` (Memory leak) | Returns classification, routing (tier **L1**, team **Application Support**), resolution-time prediction, fix accuracy, root cause, family, novelty, evidence chain | Obs |
| I5 | `GET /kb/quality` | 3,130 records, tiers 2,624 / 327 / 179 | Obs |
| I6 | `GET /escalations` | Open first. Each item includes its packet and any resolution. | Obs |
| I7 | `POST /incidents/resolve` on the tape-robot text | `top_resolution: null`, novelty true | Obs |

---

## 13. The automated tests, explained

The project has **64 automated tests** in `tests/`.
- **46 "unit" tests** need nothing but the code. I ran them: **all 46 passed** (about 3 seconds).
- **18 "integration" tests** use the real search engine, models and API. The build tracker records the whole
  suite passing at the time it was written. **I did not re-run these 18** (running them next to the live engine
  could clash on the shared search database).
- Tests **never touch your real data**: they use a temporary database and block writes to the real vector
  store and pattern files.

**Run them**

```
venv\Scripts\python.exe -m pytest -m "not integration"      # 46 quick tests
venv\Scripts\python.exe -m pytest                            # all 64 (needs built data + models)
```

### 13.1 Data preparation (`test_data_preprocessing.py`, 8 tests)

| Test | In plain words | Why it matters |
|---|---|---|
| day-first dates | `5/2/2012` is **5 February**, not 2 May; `29-03-2012` also works; blanks stay blank | A wrong date order would scramble every timeline. |
| corrupted handle time | Weird values like `3,87,16,91,111` are *labelled corrupted*, not trusted | The raw file has broken numbers. |
| placeholders | `NS` -> "Not Set", `#MULTIVALUE` -> "Multiple", `#N/B` -> "Not Available", "5 - Very Low" -> 5, Dutch closure codes translated | Junk values become clear, honest values. |
| structured transform | No rows dropped; durations **recomputed from timestamps**; each field tagged original/derived/missing; reopen flag derived | Trust the timestamps, not the corrupted column. |
| priority consistency | Flags rows where Priority is not min(Impact, Urgency) | A real data-quality signal. |
| category contradiction | "Database Timeout" labelled *Hardware* is **corrected from the text**, but the original is **kept** | Fix the error, never erase evidence of it. |
| detect files by content | A file named `incidents_text.csv` is recognised as the *structured* one | The two input files have swapped names. |
| one incident = one chunk | Short incidents are one record; long text (over 300 words) is split **only at sentence ends** | Keeps a symptom together with its fix. |

### 13.2 Fingerprint and causal chain (`test_fingerprint_and_causal_chain.py`, 8 tests)

| Test | In plain words | Why it matters |
|---|---|---|
| query fingerprint | "After the new version was deployed, users in production cannot log in ... all users affected" gives symptom *login failure*, trigger *deployment / release*, environment *Production*, scope *organization-wide*; root cause stays **Unknown** | Extract what is said; invent nothing. |
| provenance follows text | Root cause taken from AI-written text is tagged **synthetic**; from real text, **derived** | Honesty travels with the fact. |
| closure-code fallback | Note is just "closed" -> root cause "hardware fault (per closure code)", tagged derived | A weaker source is used, and labelled as such. |
| dimension match | Matching a fingerprint field against a family's shares returns 1.0, 0.7, or "not applicable" | Handles unknowns cleanly. |
| causal-chain tags | Trigger backed by a real related-change = **observed**; text-based failure/symptom = **inferred**; impact = **derived**; outcome from real timestamps = **observed** | Three kinds of link must never look alike. |
| original text = observed | With real text, symptom/resolution = observed | Tag depends on source quality. |
| no timestamps, no chain | Without times no chain is built; facts are shown unordered with a reason | A chain implies order; no order, no chain. |
| empty stages | Stages with no data say **"insufficient evidence"** | Never fill gaps. |

### 13.3 Patterns, novelty, correlation (`test_patterns_novelty_correlation.py`, 6 tests)

| Test | In plain words | Why it matters |
|---|---|---|
| clustering | Three well-separated groups are found as **exactly 3 pure families** | The grouping method works when the answer is known. |
| cross-symptom root cause | "app is slow" and "app freezes" with the same root cause are reported as one root cause, 2 symptoms | Different words, one cause. |
| novelty model | Strong signals give P(known) above 0.99; weak signals below 0.01; **with no calibration the verdict is "undetermined"** | The threshold must be fitted, not hand-picked. |
| degraded retrieval | Un-reranked results give "undetermined" | Don't judge with missing signals. |
| threshold rule | Chosen threshold keeps the false-novel rate at or below 2% and catches every novel item on clean data | The selection rule really does what it claims. |
| correlation | Two DB tickets 5 min apart alert (latency **300 s**); printer and VPN tickets don't join; a DB ticket at 80 min is outside the 30-min window | Burst yes, noise no, expired no. |

### 13.4 Query evaluation (`test_query_evaluation.py`, 8 tests)

| Test | In plain words |
|---|---|
| clear known query | Grades **Good**; the four components are relevance, known, pattern, fix. |
| unrelated query | Grades **Poor** with a reason ("...recognised..."). |
| novel is always poor | Even with a high score, a novel verdict grades **Poor**, and fix confidence is forced to 0. |
| middle score | Grades **Fair**. |
| missing signal | A signal that can't be computed is **left out** of the average (not counted as 0). |
| very short query | Tells you to add detail. |
| relevant beats unrelated (integration) | Memory-leak text is **Good**, pizza recipe is **Poor**, and the scores differ by more than 0.5. |
| endpoint agrees with analyze (integration) | `/evaluation/query` returns Good with 3 top matches; empty text gives 422; the score equals the one from Analyze. |

### 13.5 Synthetic text and quality (`test_synthetic_and_quality.py`, 6 tests)

| Test | In plain words |
|---|---|
| generation is conditioned | Every AI-written story is compatible with the **real** ticket's CI group and closure code, and each real row is used at most once. |
| seeded defects | Low-quality notes and contradictions are planted on purpose, in differently-worded views, so the quality manager can be tested. |
| generic / empty notes | "closed" and "" are flagged; a detailed note scores above 0.8 with no flags. |
| duplicates | Identical tickets group together; very similar ones (cosine 0.95+) form near-duplicates. |
| contradictions | A "hardware fix" whose note says "installed the vendor patch" is a conflict; "no fault found" with "replaced the disk" is a conflict. |
| score order | Detailed note beats "fixed"; a reopened ticket lowers the score; a contradiction lowers it. |

### 13.6 Troubleshooting units (`test_troubleshooting_units.py`, 12 tests)

| Test | In plain words |
|---|---|
| asks when low confidence and vague | Confidence 0.2 + vague -> asks about **component** (trigger `low_confidence_vague`). |
| doesn't ask when confident or specific | Confidence 0.9, or a specific report, -> no question. |
| never asks known fields or twice | Known component skipped; answered scope skipped; a second question is refused. |
| ambiguous families | Two families 0.50 vs 0.46 with different components -> asks; if 0.50 vs 0.20 -> no question. |
| pre-escalation and answer parsing | About to escalate -> asks about **trigger**; "yes, after a deployment" understood; "only me" -> single user; "it's in prod" -> Production; "no" -> no recent change; empty -> nothing. |
| attempt tracking | New attempt starts **PENDING**; "failed" becomes **FAILED** and excluded; answering twice or answering "MAYBE" is an error; attempts are kept in order. |
| destructive needs 2 sources | "Restored the table from backup" with 1 source is **not allowed**; with 2 it is allowed *with* human confirmation; "Restarted the service" is flagged disruptive. |
| ranking | One top pick; confidence **equals** relevance x agreement x provenance; the note "closed" is skipped; excluding the top strategy gives the next; un-reranked gives confidence "undetermined". |
| family prior | A confident family match pulls that family's strategies to the top. |
| action extraction | From "...resolved by restarting the application service. As a result, response times are back to normal." it pulls the action and the "what you should see" clause; a Wilson interval brackets a 5% rate. |
| ranking metrics | MRR, precision@k, hit@k, nDCG, context precision compute correctly on small examples. |
| clustering metrics | Purity is 1.0 for perfect clusters; pairwise precision 2/6 when everything is lumped into one. |

### 13.7 Integration tests (`test_integration.py`, 16 tests; not re-run by me)

| Group | Test | In plain words |
|---|---|---|
| Retrieval | demo query finds memory-leak family | Top results vote for a family named "memory leak"; the vague-to-technical step added "memory leak". |
| | filters and exclusions | Priority 3 filter returns only priority 3; an excluded incident never appears. |
| | duplicates collapsed | "Encoder crashed during media conversion" collapses 10+ identical tickets into one. |
| Fallbacks | no AI key | Labelled retrieval-only mode; still returns a top resolution. |
| | embedding fallback | Bad cloud provider -> local model, 384-number vectors. |
| | reranker missing | "unreranked" and **no** confidence numbers. |
| | vector DB unreachable | "keyword-only" label; results still returned. |
| Honesty | novel probe | "Quantum key distribution link... desynchronized" is novel; root cause and family are "insufficient evidence". |
| | evidence chain complete | Known incident has all 7 parts; strength values are computed or "insufficient evidence", between 0 and 1. |
| Workflow | fail-fail-fail loop | No strategy repeats; at most 1 question; ends **escalated**; packet history equals the steps shown and the failed list matches. |
| | next tier resolves escalation | Full loop: escalate, list, resolve, KB decision, incident Resolved, second resolve refused. |
| | escalation API validation | List returns 200; unknown ID 404; 2-letter note 422. |
| | WORKED becomes retrievable | Payroll-export fix enters the KB and is found by keyword search afterwards. |
| | poor note goes to review | "ok" note -> pending review -> reject works. |
| API | all endpoints | Health, search, analyze, incident, evidence-chain, attempts, triage, resolve, patterns, 404s, VPN storm alert, escalate, KB quality. |
| Science | evaluation reproducible | Running the same retrieval evaluation twice gives identical numbers. |

---

## 14. The report card numbers in plain English

These come from `docs/EVALUATION.md` (computed by `scripts/run_evaluation.py`, run of 2026-09-28). They are
tests of the *system*, not of one query.

**The honest caveat first:** about 95% of the library text is AI-written, so these scores describe how the
app does **on this library**, not on any real company's tickets.

| Area | Number | What it means |
|---|---|---|
| **Finding the right past incident** | Top result is relevant **89.5%** of the time; a relevant one is in the top 5 **93.4%** of the time | The search is strong. Hybrid + re-rank beats either search alone (MRR 0.911 vs 0.864 keyword-only). |
| Vague reports | 87% have a relevant result in the top 5, versus 97.7% for lay wording | Vague reports are harder, as expected. |
| **Right family** | **89.1%** | Puts the incident in the correct pattern family almost 9 times in 10. |
| **Right *fix*** (strategy accuracy) | **39.5%** | The weakest headline number: choosing the exact *way of fixing* is hard because each problem has 2 or 3 valid fixes. That's why alternatives are shown and troubleshooting has several rounds. |
| Does confidence mean anything? | Fix right only 11% of the time at confidence up to 0.25; about 55% at 0.5 to 0.75 | Higher confidence really is more often right. |
| **Novel detection** (test set) | Catches **100%** of new incidents; wrongly calls a known one novel **0.8%** of the time (1 of 129) | Very good. Only 21 novel probes were tested, so "indicative", not "proven". A simpler single-signal method caught 81%. |
| **Finding families** | 30 families, purity **91%** | Groups are mostly clean. Without the enriched fingerprint, purity is 68%. |
| **Guided troubleshooting** (simulated) | Resolved **76%**, first step right **39.5%**, avg **1.63** steps, escalated **23%**, asked a question in **50%** of sessions, never more than 1 | Most sessions end in a fix; the loop is doing its job. |
| **Live correlation** | Caught **100%** of bursts; **78%** of alerts were correct; **22%** false alarms; detected after about **4.4 minutes** | Good at not missing, weaker at not over-alerting. Hence "possible correlation: confirm". |
| **Evidence chain** | Complete for **99.2%** of known incidents; 0% "complete" for novel ones (by design) | Novel incidents deliberately have no fabricated evidence. |
| **Quality manager** | Finds 100% of the planted "closed / fixed" notes, but only **16% precision** on contradictions (many false flags) | Weakest check, reported as-is. Needs an AI judge to improve. |
| **Text classifiers** | Category **96.3%** correct | Category is easy. Priority/impact/urgency are only 54 to 57%, which is actually lower than always guessing the most common answer (about 60%), so do not lean on them. |
| **Time to resolve** | Off by about **16.5 h** (median), R-squared about 0.05 | Almost unpredictable. The UI shows a range (P25 to P75), not a promise. |
| **Will it be reopened?** | ROC-AUC **0.83**; the riskiest 10% are reopened 4.5x more often | Useful as a warning signal. |
| **AI-written text (LLM mode)** | Only **28%** of AI sentences were confirmed by a fact-checking model, though 72.5% passed the built-in "grounded" check | The main reason the default answer is copied from history, not written by AI. |

---

## 15. Honest limits

1. **Most text is synthetic.** Real tickets had no descriptions. Confidence is capped by design (about 0.8).
2. **Exact fix choice is only about 40% right on the first try.** Alternatives and 3 rounds exist for this.
3. **No step-sequence data**, so "what usually comes next" is *not* claimed.
4. **No assignee or team data**, so no individual is ever recommended.
5. **No environment field** in the sources, so `environment` stays Unknown unless you say it.
6. **The novelty test set is small** (about 20 novel items per split).
7. **Resolution-time prediction is weak**; it is shown as a range.
8. **Contradiction detection** has low precision.
9. **No phone layout.** **No Docker** (removed on request); it runs as local processes.
10. **The new website has no Live Correlation page**; use the API or the older Streamlit app.
11. **Decision support only.** It never changes a real system.

---

## 16. Why did it do that? (FAQ)

**Why did it say "Novel" for my pizza question?** It has no idea whether text is an IT incident; it only
sees that *nothing in the library is similar*. Result: P(known) about 0.0002, red bar, Poor grade.

**Why is there no recommended fix?** Either the incident is novel (no forced fix), or every candidate was
skipped (generic notes), banned (already failed) or blocked (destructive with under 2 sources).

**Why is the confidence never above about 0.8?** Because it is multiplied by 0.8 for AI-written evidence, and
nearly all evidence is AI-written. It is the honest ceiling.

**Why did it suggest something so similar to what I just tried?** It should not. Steps whose text is at least
0.5 similar to a failed step are dropped. If you see a near-repeat, that is a bug worth reporting.

**Why did it ask me a question?** One of three reasons: low confidence on a vague report, two families tied,
or you are about to escalate. It asks at most once.

**Why did my fix go to "Manual review"?** Its quality score was under 0.55, usually a very short or generic
note such as "ok" or "fixed". Write what you did, what caused it, and how you verified it.

**Why does the confidence differ from an earlier run?** The library grows as fixes are added, and the
evidence changes slightly.

**Why is there a banner about "Retrieval-only mode"?** No AI writer is available. Everything shown is from
history and maths. Nothing is lost except optional AI wording.

**Why is a restart marked "needs human confirmation"?** Restarts interrupt users. The app is decision
support, so a person confirms anything disruptive.

**Why are some words amber or dotted?** Amber "synthetic" means AI-written from real ticket facts. Dotted
means an inferred (guessed) link. Dashed means derived. Solid means observed. Line style repeats the
colour so nobody depends on colour alone.

**Why two frontends?** The original brief asked for Streamlit; the Next.js site replaced it as the main
screen. Streamlit (`streamlit run frontend/app.py`) is kept as the spec-compliant fallback and has the
Live Correlation page but no Escalations page.

---

## 17. Appendices

### A. API cheat sheet (Swagger at <http://localhost:8000/docs>)

| Method and path | What it does |
|---|---|
| `POST /incidents/search` | Search only, with verdict and evidence chain |
| `POST /incidents/analyze` | Full analysis (the Assistant button) |
| `POST /incidents/triage` | Classification, routing, tier, time and reopen predictions |
| `POST /incidents/resolve` | The ranked top fix, alternatives, strategy panel |
| `POST /incidents/troubleshoot` | `action`: start / respond / clarify / escalate / state |
| `POST /incidents/feedback` | Ratings, reasons, four questions |
| `POST /incidents/escalate` | Build an escalation packet |
| `GET /escalations`, `POST /escalations/{id}/resolve` | The L2/L3 inbox and closing an item |
| `POST /incidents/simulate`, `GET /incidents/correlations` | Live correlation |
| `GET /incidents/{id}`, `/evidence-chain`, `/attempts` | One record, its evidence, its attempts |
| `GET /patterns`, `/patterns/{id}`, `/patterns/graph` | Families |
| `POST /postmortem` | Structured postmortem, then knowledge-base update |
| `GET /kb/quality`, `/kb/evolution`; `POST /kb/evolve`, `/kb/review/{id}` | Library health, audit trail, batch, approve/reject |
| `POST /evaluation/query`, `GET /evaluation`, `GET /health` | Grade one query, whole-app report card, system status |

### B. Where things live

```
backend/
  api/routes.py            the web endpoints
  services/                the "brain" that ties steps together (platform, analysis, triage, escalation, postmortem)
  retrieval/               understand query, embeddings, keyword index, vector store, merge, re-rank
  intelligence/            fingerprint, patterns, causal chains, novelty, correlation
  rag/                     resolution ranking (confidence), strategies, safety guardrails, AI text
  troubleshooting/         the step loop, attempt records, clarifying questions
  agents/                  three cooperating agents: Pattern -> Diagnostic -> Escalation
  knowledge/               quality manager, library updates
  evidence/                the "why" trail
  evaluation/              query grader, calibration, report card
  data_pipeline/           cleaning, AI-written text, chunking
web/                       the new website (Next.js)
frontend/                  the older Streamlit app
data/processed/            built library, indexes, models, database
data/evaluation/           test queries, results, calibrated thresholds
docs/                      design, evaluation, fallbacks, dataset reports, recorded checkpoints
tests/                     the 64 automated tests
```

The three agents (`backend/agents/`) hand work to each other with typed messages: the **Pattern Intelligence
agent** reads and matches; the **Diagnostic agent** picks and tracks steps; the **Escalation agent** builds
the packet. Each has a different set of tools on purpose.

### C. Settings that change behaviour (`.env`)

| Setting | Default | Effect |
|---|---|---|
| `LLM_API_KEY` | blank | Blank means Retrieval-only mode |
| `LLM_PROVIDER` / `LLM_MODEL` | openai / gpt-4o-mini | Which AI writer |
| `EMBEDDING_PROVIDER` | local | local, openai or nvidia (falls back to local) |
| `RERANKER_PROVIDER` | local | local, nvidia or none |
| `ESCALATION_TIERS` | `L1,L2,L3` | Tier order |
| `CHROMA_MODE` | embedded | embedded or a Chroma server |
| `TROUBLESHOOTING_MAX_ROUNDS` | 3 | Step cap |
| `CLARIFICATION_CONFIDENCE_THRESHOLD` | 0.45 | "Low confidence" line |
| `CORRELATION_WINDOW_MINUTES` / `..._MIN_INCIDENTS` | 30 / 2 | Correlation window and alert size |
| `KB_QUALITY_THRESHOLD` | 0.55 | Pass mark for joining the library |

> Thresholds that came from testing (the novelty cut-off 0.4896, the correlation similarity 0.9, the
> re-ranker calibration) live in `data/evaluation/calibration.json`, **not** in the code.
> To rebuild everything: `python scripts/build_all.py`, then `python scripts/run_evaluation.py`.

### D. If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| "Could not load this view" everywhere | Engine not running | Start Terminal 1 again; check the status light |
| Analyze takes a few seconds | It searches and re-ranks thousands of records | Normal |
| Very slow first start | Models loading | Wait for "Application startup complete" |
| Confidence shows "undetermined" | Re-ranker off | Check `/health` and `RERANKER_PROVIDER` |
| Two programs fighting over the search database | Embedded ChromaDB isn't safe for two writers | Run one at a time, or use a Chroma server (`CHROMA_MODE=http`) |
