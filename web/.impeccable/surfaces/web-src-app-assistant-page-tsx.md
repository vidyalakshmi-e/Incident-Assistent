---
version: 1
slug: "web-src-app-assistant-page-tsx"
primary_target: "web/src/app/assistant/page.tsx"
related_targets: ["web/src/app/troubleshooting/page.tsx","web/src/app/escalations/page.tsx","web/src/app/correlation/page.tsx","web/src/app/novelty/page.tsx","web/src/app/patterns/page.tsx","web/src/app/knowledge/page.tsx","web/src/app/feedback/page.tsx","web/src/app/evaluation/page.tsx"]
---

## Scope and mode

The Next.js desk in `web/`: all eleven routes (assistant, troubleshooting, escalations, correlation, novelty, patterns, family, knowledge, feedback, evaluation, incident record). Mode: Operate. Desktop only (owner's decision): no phone layout, 1200px minimum width.

## Audience, task, proof

Evaluators walking the README demo; the fiction is an L1/L2 engineer mid-incident. Task per screen: read the verdict, act on one ranked step, follow any ID to its record. On Escalations the reader is the L2/L3 engineer: read what was tried, record what fixed it. Proof is live API data only: calibrated relevance, computed confidence (shown as its equation), real reopen statistics, evaluation JSON. Never invent numbers.

## Direction and memorable moment

Analog Forecast Desk (seed b3f75bba). Memorable moment: the analog chart. Known incidents draw a ring of stations around the 0.95 contour; novel incidents leave every station on the rim. The verdict owns a flat colour field (cobalt known, red novel) and closes with an issuance line (analysis ID, UTC issue time). Once a report is analysed it folds to a one-line strip, so the verdict, the fix heading and the analog stations share the 1440x900 first viewport. Red is for novel and alert (correlation alerts included); amber is for escalation, caution and synthetic provenance. Notices are flat bands with a printed grade word (Note, Caution, Alert); nothing else invents a grade.

## Constraints

Labels "Why did the system recommend this?" and "Simulate incoming incidents" follow prompt.txt. Provenance never by colour alone. No em-dashes in UI text (backend strings pass through clean()). No kicker labels above headings: headings lead, attribution follows. Streamlit UI in frontend/ is kept as the spec fallback.

## Open decisions

None blocking. Postmortem generation mutates the knowledge base by design (demo loop).
