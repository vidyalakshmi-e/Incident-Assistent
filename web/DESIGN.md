---
name: Incident Intelligence
description: An analog forecast desk for incidents; every verdict read from historical analogs, with its odds and its provenance.
colors:
  chart-paper: "#f1f5f6"
  rail-paper: "#e5ebee"
  plotting-sheet: "#fafcfc"
  blue-black-ink: "#101820"
  ink-secondary: "#3a4753"
  ink-tertiary: "#56636f"
  hairline: "#d2dade"
  rule-strong: "#a3afb9"
  cobalt: "#2447d5"
  cobalt-hover: "#1a37b3"
  cobalt-soft: "#e1e7fb"
  cobalt-fill: "#2447d5"
  cobalt-fill-hover: "#1a37b3"
  on-cobalt: "#f4f6ff"
  alert-red: "#c23a2e"
  red-soft: "#f8e1de"
  red-fill: "#c23a2e"
  on-red: "#fff6f4"
  caution-amber: "#dda01e"
  on-amber: "#14110a"
  amber-ink: "#7a5000"
  amber-soft: "#f6ebcd"
  inferred-violet: "#7040ab"
  violet-soft: "#ece4f6"
  derived-teal: "#0d6d65"
  teal-soft: "#dcefec"
  missing-gray: "#687480"
typography:
  display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "29px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.015em"
    fontVariation: "\"wdth\" 116"
  headline:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "27px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.015em"
    fontVariation: "\"wdth\" 116"
  numeral:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.015em"
    fontFeature: "\"tnum\", \"lnum\""
    fontVariation: "\"wdth\" 116"
  title:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18.5px"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  body-small:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11.5px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.035em"
    fontVariation: "\"wdth\" 78"
  grade:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.06em"
    fontVariation: "\"wdth\" 72"
  record-id:
    fontFamily: "Geist Mono, ui-monospace, Cascadia Mono, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.025em"
rounded:
  none: "0px"
  inner: "2px"
  ctl: "3px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "28px"
  3xl: "32px"
  4xl: "40px"
  5xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt-fill}"
    textColor: "{colors.on-cobalt}"
    rounded: "{rounded.ctl}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.cobalt-fill-hover}"
    textColor: "{colors.on-cobalt}"
  button-secondary:
    backgroundColor: "{colors.plotting-sheet}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.ctl}"
    padding: "0 16px"
    height: "40px"
  button-ghost:
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "32px"
  button-ghost-hover:
    backgroundColor: "{colors.rail-paper}"
    textColor: "{colors.blue-black-ink}"
  button-danger:
    backgroundColor: "{colors.plotting-sheet}"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.ctl}"
    padding: "0 16px"
    height: "40px"
  button-danger-hover:
    backgroundColor: "{colors.red-soft}"
  input:
    backgroundColor: "{colors.plotting-sheet}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "40px"
  toggle-on:
    backgroundColor: "{colors.blue-black-ink}"
    textColor: "{colors.chart-paper}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "32px"
  toggle-off:
    backgroundColor: "{colors.plotting-sheet}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "32px"
  nav-item-active:
    backgroundColor: "{colors.plotting-sheet}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.ctl}"
    padding: "0 10px"
    height: "36px"
  verdict-known:
    backgroundColor: "{colors.cobalt-fill}"
    textColor: "{colors.on-cobalt}"
    rounded: "{rounded.none}"
    padding: "24px 28px 16px"
  verdict-novel:
    backgroundColor: "{colors.red-fill}"
    textColor: "{colors.on-red}"
    rounded: "{rounded.none}"
    padding: "24px 28px 16px"
  verdict-undetermined:
    backgroundColor: "{colors.blue-black-ink}"
    textColor: "{colors.chart-paper}"
    rounded: "{rounded.none}"
    padding: "24px 28px 16px"
  escalation-field:
    backgroundColor: "{colors.caution-amber}"
    textColor: "{colors.on-amber}"
    rounded: "{rounded.none}"
    padding: "20px 28px"
  notice-note:
    backgroundColor: "{colors.rail-paper}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  notice-caution:
    backgroundColor: "{colors.amber-soft}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  notice-alert:
    backgroundColor: "{colors.red-soft}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
---

# Design System: Incident Intelligence

## Overview

**Creative North Star: "The Analog Forecast Desk"**

Every incident is read the way a forecaster reads a chart: against historical analogs, with stated odds, and with a clear line between what was observed and what was inferred. The surface is cool chart paper with blue-black ink; colour is spent almost entirely on meaning (state, provenance, action), never on decoration. Density is that of a working desk: ruled fact rows, hairline tables, charts drawn only where real data sits under them.

The system has two sheets. Light is the day chart (projected demos, office light); dark is the night chart (on-call). Both carry identical roles; only the values shift. Flat colour fields announce state (a verdict, an escalation, an alert), and everything else stays on paper. Numbers are shown as the computation they are (confidence as its equation, relevance on contours), never as a bare hero figure in a tile.

The build refuses the dark KPI-tile observability console and the chat-bot assistant. There are no tile dashboards, no chat bubbles, no gradient hero numbers.

**Key Characteristics:**
- Cool chart-paper ground, blue-black ink, colour reserved for state and provenance.
- Flat, square state fields (verdict, escalation, correlation alert) that own their full width.
- Archivo across its width axis: wide for display, condensed caps for chart annotation, extra-condensed for grade words.
- Geist Mono for every record ID, and every ID is a link to its record.
- Provenance drawn in line style (solid, dashed, dotted) plus a word, never colour alone.
- Graticules, contours and rules only under real data.

## Colors

A cool, near-neutral paper-and-ink ground with one action colour and a small, strictly semantic set of state and provenance hues.

### Primary
- **Chart Cobalt** (cobalt): action, selection, focus rings, caret, the underline of matched phrases, the "backs the fix" barb on the analog chart, and the known-pattern state. In dark mode it lifts to a light periwinkle for text and links only.
- **Cobalt Field** (cobalt-fill, hover cobalt-fill-hover): every filled cobalt surface: the primary button, the known-pattern verdict field, text selection, a "good" segmented option. Dark mode keeps it saturated (#2f54e6) with white ink (on-cobalt) so filled fields never go pastel.
- **Cobalt Wash** (cobalt-soft): focus halo around inputs and highlighted table rows (at 60%).

### Secondary
- **Alert Red** (alert-red, red-fill, red-soft, on-red): the novel-incident verdict field, correlation alerts (red fields), failed attempts, destructive buttons, threshold markers on charts, the Alert notice band.
- **Caution Amber** (caution-amber, on-amber, amber-ink, amber-soft): escalation fields, caution notices, synthetic provenance, disruptive-action warnings. Filled amber fields always carry on-amber ink, which stays dark in both themes; amber-ink is the readable amber for text on paper.

### Tertiary
- **Inferred Violet** (inferred-violet, violet-soft): inferred provenance only (LLM output, inferred chain links), always drawn dotted.
- **Derived Teal** (derived-teal, teal-soft): derived provenance only, always drawn dashed.
- **Missing Gray** (missing-gray): absent values; drawn as an empty outline, never as a filled stroke.

### Neutral
- **Chart Paper** (chart-paper): page ground.
- **Rail Paper** (rail-paper): the navigation rail, the Note notice band, ghost hover, skeleton base.
- **Plotting Sheet** (plotting-sheet): raised working surfaces: composer, report strip, modules, the analog chart disc, inputs, secondary buttons.
- **Blue-Black Ink** (blue-black-ink): primary text, filled "same family" stations, observed provenance, the undetermined verdict field, selected toggles.
- **Secondary Ink** (ink-secondary) and **Tertiary Ink** (ink-tertiary): supporting text, then captions, annotation labels and axis values.
- **Hairline** (hairline) and **Strong Rule** (rule-strong): row rules and module seams, then control borders, table-head rules, contours and the chart rim.

### Named Rules
**The Colour Is State Rule.** Cobalt means known or action, red means novel or alert, amber means escalation, caution or synthetic. No hue is used decoratively; if a colour appears, it is asserting one of these meanings.

**The Filled Field Rule.** Any filled state surface uses the *-fill token and its on-* ink (cobalt-fill with on-cobalt, red-fill with on-red, caution-amber with on-amber). The lifted dark-mode cobalt (#7189ff) is for text links only and never fills a surface.

**The Never Colour Alone Rule.** Provenance is always line style plus a word: solid for observed or original, dashed for derived, dotted for inferred, a heavier solid amber stroke for synthetic, an empty outline for missing.

## Typography

**Display Font:** Archivo (variable width axis), with ui-sans-serif, system-ui fallback
**Body Font:** Archivo
**Label/Mono Font:** Geist Mono for record IDs (with ui-monospace, Cascadia Mono)

**Character:** One family worked across its width axis, like chart lettering: wide and tight-tracked for headings and verdict figures, regular for reading, condensed caps for the annotation printed on axes and table heads. Mono is reserved for identifiers so an ID always reads as addressable.

### Hierarchy
- **Display** (700, 29px, 1.1, width 116): page titles.
- **Headline** (700, 27px, 1.15, width 116; 24px compact): the ranked fix action and verdict state words (28px). Verdict and escalation headings use the same wide cut at 28 to 30px.
- **Numeral** (700, 34px, 1, width 116, tabular lining figures): the verdict probability and the computed confidence, always followed by the terms that produce it.
- **Title** (700, 18.5px): section titles, with a 13.5px tertiary meta line inline beside them. Disclosure summaries sit at 16.5px semibold.
- **Body** (400, 15px, 1.5): reading text; ledes and fix steps at 15.5px relaxed, capped at 62 to 70ch.
- **Body Small** (13.5px): fact labels, table cells, attribution lines, field labels (semibold).
- **Label** (600, 11.5px, 0.035em, uppercase, width 78): chart annotation, axis captions, table heads, data-term labels over their values, nav group names.
- **Grade** (800, 12.5px, 0.06em, uppercase, width 72): the printed grade word on notice bands only.
- **Record ID** (Geist Mono, 12.5px, tight tracking): every incident, family, strategy, packet and analysis identifier.

### Named Rules
**The Headings Lead Rule.** Nothing sits above a heading. Attribution (lead phrase, kind, strategy ID, family, counts) follows beneath it in body-small secondary ink. The condensed label cut labels data and axes; it is never a kicker over a title.

**The Tabular Figures Rule.** Every number in a table, fact row, chart or equation uses tabular lining numerals so columns of odds line up.

## Layout

A fixed 244px rail (rail paper, hairline right edge, painted the full page height) beside a main column capped at 1240px and padded 40px. Main content uses a 12-column grid: the ranked fix takes 7 columns beside the analog chart's 5, with 48px column gaps; secondary sections reverse to 5 / 7. Sections are separated by a hairline and 36px of top padding rather than by cards.

The first viewport at 1440x900 after an analysis holds, in order: the one-line report strip, the full-width verdict field, the fix heading and the analog stations. Before an analysis the full composer (report textarea, presets, cobalt Analyze) sits there instead; once analysed it folds to the strip with an "Edit report" control.

Spacing rhythm: 4px micro gaps inside labels and value pairs (6px between a heading and its attribution), 12px between inline controls, 16 to 20px inside fields and bands, 32 to 40px between grid columns and major blocks.

Desktop only (owner's decision, 2026-09-28). There is no phone layout: the shell holds a 1200px minimum width and never reflows, a narrower window scrolls, and the viewport is declared 1280px wide so a phone shows the desktop page zoomed out.

## Elevation & Depth

Flat by default. Depth comes from tonal layering (chart paper, rail paper, plotting sheet) and hairline rules. The few shadows that exist are low, cool (tinted by the shade token, hsl 210 40% 18% in light, near-black in dark) and small.

### Shadow Vocabulary
- **Press lip** (`box-shadow: 0 1px 0 hsl(var(--shade)/0.18), 0 2px 6px -2px hsl(var(--shade)/0.35)`): the primary button only.
- **Sheet lift** (`box-shadow: 0 1px 0 hsl(var(--shade)/0.04), 0 8px 24px -18px hsl(var(--shade)/0.4)`): the report composer, the one surface that invites writing.
- **Selected tab** (`box-shadow: 0 1px 2px hsl(var(--shade)/0.12)`): the active rail nav item and the selected theme option.
- **Focus halo** (`box-shadow: 0 0 0 3px var(--cobalt-soft)`): inputs on focus; other elements take a 2px cobalt outline offset 2px.

### Named Rules
**The Paper Stays Flat Rule.** State fields, notices, charts, tables and modules never cast shadows. A shadow means "you can press or write here", nothing else.

## Shapes

Two corners only. Controls and panels (buttons, inputs, selects, toggles, preset chips, nav items, segmented controls) take a barely-softened 3px radius; segments inside a control take 2px. Everything that carries state or data is square: verdict and escalation fields, notice bands, correlation alerts, the report strip, tables, fact rows, modules and chart frames. Circles appear only as chart marks (stations, the incident centre, the relevance rim and contours).

Borders are 1px hairlines. Modules pack edge to edge with 1px seams (a 1px gap over a hairline ground) rather than floating as padded cards. Empty states use a dashed strong-rule border.

## Components

### Buttons
Compact and decisive; a 1px press on activation.
- **Shape:** gently squared (3px).
- **Primary:** cobalt field with on-cobalt ink, semibold, heights 32 / 40 / 44px (sm / md / lg) with 12 / 16 / 20px side padding and 13.5 / 14.5 / 15px text, press-lip shadow. One primary per view: Analyze, Troubleshoot, Submit.
- **Hover / Focus:** hover deepens to cobalt-fill-hover; focus is a 2px cobalt outline offset 2px; active translates 1px down; disabled drops to 45% opacity. Transitions 150ms ease-out.
- **Secondary:** plotting sheet with a strong-rule border; hover darkens the border to tertiary ink.
- **Ghost:** secondary ink, no border; hover fills with rail paper. Used for "Edit report" and in-context tools.
- **Danger:** plotting sheet, red text, red border at 55%; hover fills red-soft.
- **Busy:** a 2px sweeping bar replaces the icon; no spinners.

### Chips and Toggles
- **Style:** 28px (presets) or 32px (filters), 3px radius, 1px border. Off: hairline or strong-rule border, secondary ink. On: filled blue-black ink with paper text.
- **Segmented:** a radio group in a bordered 3px track; the selected segment fills ink, or cobalt-fill for a "good" answer, red-fill for a "bad" one.

### Cards / Containers
There are no cards. Containers are one of:
- **Fact rows:** label left (13.5px secondary ink, optional 12px sub-line, amber-ink when weak), tabular value right (15px semibold), a hairline between rows, a strong rule on top. These replace KPI tiles everywhere.
- **Module grid:** plotting-sheet modules (16px by 14px padding) seamed by 1px hairlines. Reserved for modules that hold a real distribution chart.
- **Disclosures:** a hairline-topped native details row, 16.5px semibold summary with a caret that rotates 90 degrees (180ms), body indented 27px; the open height animates over 220ms.

### Inputs / Fields
- **Style:** plotting sheet, 1px strong-rule border, 3px radius, 40px high (textarea 15.5px relaxed), placeholder in tertiary ink, cobalt caret.
- **Focus:** border turns cobalt with the 3px cobalt-soft halo; hover darkens the border to tertiary ink.
- **Error:** a 13px medium red message replaces the hint beneath the field.
- **Composer:** the report textarea sits borderless inside a sheet-lift panel at 17px, auto-sized to content, with presets and the primary button in a hairline-ruled footer.

### Navigation
- **Rail:** grouped links (Operate, Understand, Improve) under condensed-caps group labels; 36px rows, 14.5px text, 18px line icons. Active: plotting-sheet fill, semibold ink, selected-tab shadow, bold cobalt icon. Hover: chart-paper fill.
- **Rail footer:** the live station status, a one-line decision-support disclaimer, the theme toggle.
- **Tabs:** 14px semibold, tertiary ink at rest; the selected tab takes a 2px cobalt underline; arrow keys move selection.
- **Open count:** the Escalations link carries the number of open escalations at its right edge, in amber-ink tabular figures, because that is work waiting for L2/L3.

### Notice Bands
Flat, square bands like a forecast-office bulletin. A printed grade word from the closed set **Note** (rail paper, secondary ink), **Caution** (amber-soft, amber-ink) and **Alert** (red-soft, red) sits in its own 7.5rem column; the message follows beside it with a semibold lead sentence; an optional action sits at the end. No icons, no radius, no other grade words.

### Verdict Field
A full-width flat field that owns its colour: cobalt-fill for a known pattern, red-fill for a novel incident, ink for undetermined. Three columns (state word, the matched family or route, the probability against its validated threshold), separated by a 25% current-colour rule. It closes with an issuance line under a 20% rule: the analysis ID as a mono link, the UTC issue time, and the validity statement.

### Escalation and Alert Fields
Escalations are a flat caution-amber field with on-amber ink, the tier in the wide display cut and the packet ID in mono. Correlation alerts are red-fill fields with on-red ink, with the same grade-column grid as notices.

### Escalations Page
Where L2/L3 answers an escalation. Master and detail on the 12-column grid: the Open list (with its waiting count) and the Resolved list take 4 columns as hairline-ruled rows (the incident summary clamped to two lines, then tier, team and time); the selected escalation takes 8. The detail leads with the incident summary as its heading, then who it went to and why, then ruled rows for likely root cause, suggested next step and what already failed (struck through in red, never to be repeated). An open escalation ends with a "Record the fix" panel: "What fixed it?" (required, at least a sentence), an optional root cause and the primary "Mark resolved". A resolved one shows a Note band saying who resolved it, the fix, and what happened in the knowledge base (indexed, waiting for review, or unchanged). The full packet sits in a disclosure underneath.

### Analog Chart
The signature chart. The incident under analysis sits at the centre; each retrieved analog is a station at distance 1 minus relevance on a log scale (K = 100), so known matches ring the 0.95 contour and novel incidents leave every station on the rim. Dashed contours at 0.95, 0.9, 0.75 and 0.5 carry their values in isobar-style gaps on the horizontal axis; the rim stays unbroken with its 0 printed outside. The upper half holds the matched family (filled ink stations), the lower half every other analog (open stations); a short cobalt barb marks analogs that back the fix. Hover or focus turns a station cobalt and prints its mono ID. A legend and a plain-language caption explain the scale.

### Station Plot and Front Chain
The fingerprint is a station plot: ten fields hang off a station circle whose fill shows the share of known fields, each spoke drawn in its field's provenance notation. The causal chain is a front: six stages joined by segments drawn solid, dashed or dotted by evidence tag, always horizontal. Unknown values stay "unknown" or "Not established"; nothing is invented.

### Record IDs
Geist Mono 12.5px, ink with a strong-rule underline at 3px offset; hover turns text and underline cobalt. Every ID resolves to its record, family or strategy.

## Do's and Don'ts

### Do:
- **Do** give every filled state surface its *-fill token and on-* ink; keep filled cobalt saturated (#2f54e6) in dark mode.
- **Do** lead with the heading and put attribution beneath it in 13.5px secondary ink.
- **Do** use ruled fact rows (Facts) for key figures; use the hairline module grid only when a module holds a real distribution chart.
- **Do** show confidence as its equation: the 34px figure, then "=" and each component with its label.
- **Do** mark provenance with line style plus a word: solid observed, dashed derived, dotted inferred.
- **Do** keep one desktop layout: no phone reflow, no stacked tables, a 1200px minimum width.
- **Do** fold the composer to a one-line report strip with "Edit report" once an analysis exists.
- **Do** close every verdict with its issuance line: analysis ID link and UTC issue time.
- **Do** honour reduced motion; chart entrances (700 to 750ms, ease-out-expo) and disclosure motion collapse to instant.

### Don't:
- **Don't** place a kicker or eyebrow label above any heading.
- **Don't** build KPI tiles or oversized hero numbers; the build replaced them with fact rows.
- **Don't** use rounded callouts with icons for notices, or invent a grade word outside Note, Caution and Alert.
- **Don't** use red for anything but novel, alert, failure or destruction, or amber for anything but escalation, caution or synthetic provenance.
- **Don't** fill a surface with the dark-mode text cobalt (#7189ff), or put light ink on an amber field.
- **Don't** encode provenance by colour alone.
- **Don't** draw graticules, contours or gridlines where there is no real data under them.
- **Don't** round state fields, notices, tables or charts; only controls take the 3px corner.
- **Don't** use chat bubbles or a conversational assistant frame.
