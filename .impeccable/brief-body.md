## Scope

The Mango console at `/console`: register of incidents, open case (activity, comments), and the
AI investigation. Visitor mode: Operate, serving an on-call engineer mid-incident and a
technical reviewer reading the project for a minute, weighted equally.

## Direction contract

THESIS: The register is a drawer, not a table. Incidents are typed cards packed on edge
behind tab guides, flipped from the keyboard; one card lifts clear and opens. It refuses the
icon-rail-plus-stat-tiles dashboard this category always ships, and refuses cards-as-page-
structure: the drawer is one object, not a deck of panels.

OWN-WORLD: Cold steel-green cabinet ground (#1b201f / #242a29) against bone card stock
(#e4e1d6) with typewriter ink (#16140f). One accent, violet stamp ink (#5b21b6), used only
for stamps and actions. Severity owns amber through deep red and nothing else may. Hairline
rules, boxes inside boxes, tracked caps legends, tabular figures. Archivo for the cabinet's
engraved labels, Courier Prime for anything typed or measured. A hatch system carries
confidence; crossed hatching at ninety degrees marks contradicting evidence.

STORY: The visitor sees a working drawer, understands within seconds which incidents are
burning, opens one, and finds an investigation that shows its work: five agents with their
own reasoning, findings, a probable cause carrying a visible confidence, and the evidence
numbered beneath it.

FIRST VIEWPORT: Full-height drawer on the left, roughly a third of the width, incident cards
packed on edge with severity tab guides standing proud of the pack and case numbers at
monumental scale in the margin. On the right, the open card lifted clear: typed header, status
stamped across it, then the investigation record. Above both, a thin cabinet rail carrying the
Mango plate, the filter set, and the day's remaining LLM budget. Primary action, RUN
INVESTIGATION, sits stamped at the head of the investigation block.

FORM: The Catalogue Drawer, candidate 7 of the re-rolled grounded list, seed key 287ea575,
re-roll round 1. Raised by four donations: hatch density as confidence and crossed hatch as
contradiction (exposure record); states stamp themselves and nothing is deleted (ticket
wallet); one message per line and monumental scale for the number that matters (terminal
wayfinding); every conclusion paired with the exhibit proving it (neutral software surface).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Constraints

- Single static HTML file, vanilla JS, no build step, served by FastAPI.
- Console auth is deferred by the user; the surface must work in development without a login
  and keep a clean seam for one.
- Severity colours are data, not decoration, so the identity accent may never be amber or red.
- Night use on a secondary monitor: WCAG AA contrast and full keyboard operation are the floor.

## Unresolved

- Login surface, deferred to a later round.
