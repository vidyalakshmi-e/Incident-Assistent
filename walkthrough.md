# Walkthrough: how the app works and how to use it

## What this app does

When something breaks in IT ("the app is slow", "users can't log in"), a support engineer wants to know
four things fast: has this happened before, what fixed it last time, what should I try first, and who
do I hand it to if that doesn't work.

This app answers those questions by comparing a new problem with a library of past incidents. It
recommends **one** thing to try first and shows the evidence behind it. It then guides you step by
step, and hands the problem to a senior engineer (L2 or L3) if nothing works. Every fix that works is
added back to the library, so the next person benefits.

It helps a person decide. It never changes anything on a real system by itself.

## How it works, in five steps

1. **You describe the problem in plain words.** Vague is fine, like "the system feels slow".
2. **It finds similar past incidents.** It searches about 3,100 past incidents by meaning and by
   keywords, then ranks the closest ones.
3. **It decides: known or new?** If the problem looks like a known type (a "pattern family", such as
   *memory leak*), it recommends the fix that worked most often. If nothing is similar enough, it says
   **Novel incident** instead of guessing.
4. **It guides you through fixes.** You try a step and say whether it worked. If it failed, that fix
   is never suggested again and you get the next best one. After three failed tries it may ask you one
   question, and if that doesn't help either, it escalates.
5. **It learns.** When something is fixed, either by you or by the L2/L3 engineer, the fix goes through
   a quality check and joins the library.

## Start it

You need two terminals, both opened in the project folder.

```
# Terminal 1: the engine (API)
.venv\Scripts\activate
uvicorn backend.main:app --port 8000
```

Wait until it prints `Application startup complete`. The first start takes a minute while it loads its models.

```
# Terminal 2: the screens (web app)
cd web
npm install        # first time only
npm run dev
```

Open **http://localhost:3000** in a browser on a laptop or desktop. The app has no phone layout.

No AI key is needed. Without one, the app runs in **Retrieval-only mode**: everything it shows comes
from past incidents and calculations, and nothing is written by an AI. A band at the top of each
result says so.

## A 10-minute tour

The menu on the left lists every screen. Here they are in the order that tells the story best.

### 1. Assistant: "what is this, and what do I try first?"

1. Click the **Memory leak** example, then **Analyze**.
2. A coloured bar gives the verdict. **Blue: Known pattern** means it matched a family of past
   incidents. **Red: Novel incident** means nothing similar exists.
3. Below it is the **one recommended first step**, such as *Restarting the application service*,
   with its **confidence** worked out in front of you. It also shows how often this fix held up in
   the past and which past incidents back it.
4. Under the verdict, a one-line **Query evaluation** grades this query as **Good**, **Fair** or
   **Poor**: how well the library can answer it. **Details** opens the full breakdown.
5. Scroll down for more detail:
   - how the app read your words;
   - what it pulled out of them, such as component and symptom;
   - the likely root cause;
   - **Why did the system recommend this?** (the full evidence trail).

Now try the **Tape robot (unseen)** example. The bar turns red and the evaluation is **Poor**: the app
says it has no playbook and suggests a fresh investigation instead of forcing a weak match.

### 2. Troubleshooting: "walk me through it"

1. From the Assistant, click **Start guided troubleshooting**. You can also open Troubleshooting from
   the menu and click **Start troubleshooting**.
2. You see one step. After trying it, answer **It worked**, **It failed** or **Not sure**.
3. Each **It failed** crosses that step out on the track at the top, and the app offers the next best
   step. A failed fix is never offered again.
4. After three failures the app may ask **one** short question, such as "Did this start after a recent
   deployment?", to try one last targeted step.
5. If nothing works, it **escalates**. It builds a hand-off packet: what the problem is, everything
   already tried, the likely cause, which team should take it, and what to check next. A band says
   **Waiting for L2** with a button, **Open in Escalations**.

If you answer **It worked** instead, click **Generate postmortem and update the knowledge base**. The
fix becomes part of the library.

### 3. Escalations: "the senior engineer's side"

This is the L2/L3 engineer's screen. The number next to **Escalations** in the menu is how many are
waiting.

1. Pick an escalation from the **Open** list on the left.
2. Read the right side: the problem, why it was escalated, the likely root cause, the suggested next
   step, and what was **already tried and failed** (crossed out, so nobody repeats it). The full
   hand-off packet is at the bottom.
3. Once the problem is actually fixed, write **What fixed it?**. Add the root cause if you found it,
   then click **Mark resolved**.
4. The escalation moves to **Resolved**, and the fix goes through the same quality check as any other.
   The page then tells you whether the fix was added to the library or is waiting for someone to
   approve it on the Knowledge base page.

### 4. Novel incidents: "is this actually new?"

Try **GPS time server** and click **Check novelty**. You get the verdict (known or novel), the
probability it is a known problem next to the cut-off, and the three nearest past incidents.

### 5. Knowledge base: "what is waiting for a person?"

New fixes that pass the quality check join the library on their own. The ones that score too low wait
under **Manual review**, where a person clicks **Approve** or **Reject**. **Recently added** lists what
has joined. **Process resolved incidents** handles any fixed incidents that are still waiting; normally
this runs every night.

### 6. Patterns: "what keeps happening?"

The app groups past incidents into about 30 **families** by what went wrong, such as *memory leak* or
*connection pool exhaustion*. The page is a plain list. Open a family to see its typical signs, its
usual chain of events (trigger, failure, symptom, impact, fix, outcome), how often it recurs, and the
different fixes used for it.

### 7. Feedback: "was the advice any good?"

Rate a recommendation: helpful or not, plus why ("wrong resolution", "outdated", …), and whether the root
cause and family were right. Bad ratings lower the weight of the past incidents that misled it. Nothing
is retrained behind the scenes; the ratings adjust the records.

### 8. Evaluation: "was that a good question?"

Every query gets its own evaluation, not one for the whole app. Type a query (or pick **Relevant**,
**Vague**, **Unseen incident**, **Unrelated** or **Gibberish**) and click **Evaluate**. A clear, relevant
report grades **Good**; an unrelated or unseen one grades **Poor**. The card shows the score and the four
signals behind it: retrieval relevance, known-pattern probability, pattern match and fix confidence.
Queries you analyse in the Assistant are evaluated too and listed underneath.

## Reading the screen

| You see | It means |
|---|---|
| **Known pattern** (blue bar) | The problem matches a family of past incidents |
| **Novel incident** (red bar) | Nothing in the library is similar enough to act on |
| **Confidence 0.43 = 0.96 × 0.56 × 0.80** | How sure the app is about its first step, shown as the calculation: best match × how much the evidence agrees × how trustworthy that evidence's text is |
| **P(known pattern) 0.994** | The chance this is a known type of problem, next to the tested cut-off |
| **original** | Came straight from the real data |
| **derived** | Worked out from real data by a fixed rule |
| **synthetic** (amber) | Text written by an AI from real ticket details, because the real tickets had no text |
| **inferred** (dotted line) | The app's best guess, not confirmed by data |
| **Caution** / **Alert** / **Note** bands | Warnings, from mild to serious. For example, **Caution** tells you a step needs human confirmation, or that the app is in retrieval-only mode |
| Underlined codes like `IM0006370` or `F001` | Every ID is a link to that incident or family |

Solid, dashed and dotted lines also mean original/observed, derived and inferred, so you never have to
rely on colour alone.

## Good to know

- **Most of the library's text is AI-written.** The real ticket data (46,606 tickets) has categories,
  times and outcomes but no descriptions, so about 95% of the text was generated from those real
  details. It is always labelled **synthetic** and counts for a bit less when ranking.
- **Escalation response was added on request.** The original brief (`prompt.txt`) only asks for the
  hand-off packet. The Escalations page is an addition so an escalated incident can be closed and
  learned from. The older Streamlit screens (`streamlit run frontend/app.py`) do not have it.
- **Desktop only.** On a narrow window the page scrolls sideways; there is no phone version.
- **Decision support only.** Anything disruptive, like a restart, is marked as needing a person to confirm.

## If something goes wrong

- **Every screen shows "Could not load this view".** The engine isn't running. Start Terminal 1 again,
  and check that the bottom of the left menu shows the system as up.
- **Analyze takes a few seconds.** That's normal; it searches and ranks thousands of records.
- **Want the full technical detail?** See `README.md` for setup and the API, and `docs/` for the
  design, evaluation and dataset reports.
