# Incident Intelligence: web UI

The primary frontend of the Incident Intelligence Platform: a Next.js app that talks to the FastAPI
backend in `../backend`. The Streamlit app in `../frontend` still works and remains the
spec-compliant fallback.

## Run

```bash
# 1. the API (from the project root)
uvicorn backend.main:app --port 8000

# 2. the UI (from this folder)
npm install
npm run dev            # http://localhost:3000
# or a production build
npm run build && npm start
```

The browser never calls the API directly: `next.config.ts` proxies `/api/*` to `API_URL`
(default `http://localhost:8000`). Point it elsewhere with `API_URL=http://host:port npm run dev`.

## Screens

| Route | What it shows |
|---|---|
| `/assistant` | Report in, verdict (known / novel), one ranked fix with its computed confidence, analog chart, fingerprint, evidence chain, strategies, causal chain |
| `/troubleshooting` | Guided, attempt-tracked session: worked / failed / not sure, one clarifying question, escalation packet, postmortem |
| `/escalations` | Escalated incidents for L2/L3: read the packet, record what fixed it (`?id=` or `?session=` selects one) |
| `/correlation` | Simulate incoming tickets; correlation alerts and the incoming stream |
| `/novelty` | P(known) against the validated threshold, signal contributions, how the threshold was chosen |
| `/patterns`, `/patterns/[id]` | Family map with shared-CI arcs, cross-symptom findings, hotspots; family signature, causal chain, recurrence, strategies |
| `/knowledge` | Quality distribution and flags, the evolution loop, recently added knowledge, manual review |
| `/feedback` | Rating, reasons and the four questions; feeds knowledge-base evolution |
| `/evaluation` | Scorecard plus every computed metric by area |
| `/incidents/[id]` | Any record: field-level provenance, fingerprint, quality, family, causal chain, attempts |

Working state (last analysis, open troubleshooting session) is kept in `sessionStorage`, so a reload
keeps the demo where it was.

Desktop only: the layout holds a 1200px minimum width and has no phone layout; a phone shows the
desktop page zoomed out.

## Design

The visual system ("Analog Forecast Desk") is documented in `DESIGN.md` in this folder. Provenance is
never encoded by colour alone: original/observed is a solid line, derived dashed, inferred dotted,
synthetic a heavy amber line, missing a hollow box.
