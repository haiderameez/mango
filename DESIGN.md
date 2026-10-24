# Design

<!-- impeccable:design-schema 1 -->

The Mango console is **The Catalogue Drawer**: the incident register is a steel drawer of
typed cards, not a table of rows. A case lifts clear of the drawer to be read. Written from
the built surface at `backend/app/static/console.html`.

## Color

Two dark grounds, and they mean different things. The **cabinet** is the application chrome —
charcoal for a night shift on a second monitor. The **card** is a slightly raised graphite
document plane: every fact the product asserts sits on a case sheet. The register still reads
as a drawer; the sheet now stays within the muted dark palette.

| Token | Value | Role |
|---|---|---|
| `--cab` / `--cab-2` / `--cab-3` | `#1d1e22` `#23242a` `#2c2d34` | drawer, rail, selected row |
| `--rule` / `--rule-soft` | `#373840` `#303138` | hairlines in the cabinet |
| `--cab-ink` / `-2` / `-3` | `#d7d7dc` `#b9b9c1` `#a2a3ad` | text on the cabinet |
| `--card` / `--card-2` / `--card-3` | `#26272d` `#2c2d34` `#3d3e47` | case sheet, block heads, rules |
| `--panel` | `#202127` | recessed panels inside a case sheet |
| `--ink` / `-2` / `-3` | `#e0e0e5` `#c5c5ce` `#a8a8b1` | typed text |
| `--stamp` / `--stamp-lit` | `#705c82` `#c7b5d7` | **the only identity accent**: filled actions and readable stamps |
| `--seal` | `#9caf9f` | the resolved seal |

Severity is **data colour and may never be used for identity**: `--sev-low #9ab0c1`,
`--sev-medium #d7b369`, `--sev-high #e49577`, `--sev-critical #e1858e`. This is why the
identity accent is purple stamp ink: severity already owns blue, amber, rust, and red.

The cabinet and case sheet sit close in value (about 1.2:1) so the surface stays quiet. Text
contrast remains separate from that surface treatment: primary copy on the sheet measures
11.7:1, supporting text measures 6.3:1, and the subdued purple stamp measures 7.8:1. The
primary action uses the darker purple (`--stamp`) with white text at 5.9:1. Severity retains
its own muted blue, amber, rust, and red values; hue is paired with a printed label and drawer
tab, never used as the sole signal.

## Typography

Two families, each doing a job the other cannot:

- **Archivo** — the cabinet's engraved labels, headings, buttons, prose.
- **Courier Prime** — anything typed or measured: case numbers, timestamps, durations, log
  messages, field values, exhibit identifiers. The case sheet is typewritten, so monospace
  here is the material, not a costume for "technical".

Fixed rem-free pixel ramp, no fluid clamps: 44px case number, 20px case title, 14.5px probable
cause, 13.5px body, 12.5px typed values, 12px legends. **12px is the hard floor for any
functional text.** Legends are tracked caps at `.1em`. `font-variant-numeric: tabular-nums`
is set globally so figures align in every column.

Weight and scale were pulled in along with the palette: headings run 500–600 rather than
600–700, the case number dropped from 56px to 44px and from full ink to `--ink-2`, and
letter-spacing came down across every tracked-caps label. Hierarchy now comes from size and
space rather than from weight and colour.

## Hatch — the one device that carries meaning

A repeating diagonal gradient, not decoration:

- `.hatch.d1 / .d2 / .d3` — increasing density is increasing **confidence**. The confidence
  readout is three cells; a `low` conclusion fills one, `high` fills three. The word is always
  printed beside it, so the meaning never depends on reading texture alone.
- `.hatch-x` — two gradients crossed at ninety degrees mark **contradicting or missing
  evidence**. It renders as a gutter band beside the text, never behind it; hatching under
  body copy was built, measured as a contrast failure, and removed.

The mechanical detector flags this as `repeating-stripes-gradient`. It is a deliberate,
documented exception: these stripes encode a value from the data, and removing them would
remove information.

## Components

Hairline rules and boxes inside boxes do the work that cards and shadows usually do. Rules are
1px except for the 2px muted-purple edge on probable cause, which links that conclusion to its
evidence. One ambient surface-elevation shadow appears under the lifted sheet and sign-in ticket,
offset and softly blurred to give each surface depth. Other shadows only indicate focus, citation,
selection, or active work.

- **`.cardrow`** — a card on edge: severity tab, case number in the margin, title, status,
  timestamp. Packed edge to edge with a hairline between, no gaps and no radius, because cards
  in a drawer touch. `aria-current` marks the open one.
- **`.guide`** — a sticky tab guide dividing the drawer by severity, standing proud of the pack.
- **`.sheet`** — the lifted dark case sheet. A restrained edge and shadow distinguish it from
  the cabinet without introducing a bright surface. It animates once, 170ms exponential
  ease-out, respecting `prefers-reduced-motion`.
- **`.stamp`** — status, rotated −1.5°, hairline border, in ink / stamp violet / seal green /
  critical red. A resolved case is stamped, never removed; a failed run is stamped and stays
  in the record.
- **`.sev` / `.lvl`** — severity and log level as tinted chips with a soft data color, a printed
  label, and a restrained outline. Never a filled block.
- **`.rows`** — the ruled label/value grid, 12px tracked-caps label against typed value.
- **`.route`** — the five agents as a route with interchange nodes: filled when done, pulsing
  when running, red when failed, each carrying its own duration.
- **`.exhibit`** — a numbered log record with level, endpoint, timestamp and its context
  fields as chips. Citations in the diagnosis light the matching exhibit.
- **`.cite`** — an exhibit reference. Clicking it scrolls to the exhibit and outlines it.
- **`.ticket`** — the sign-in surface, written as a reader's ticket: the same ruled
  label/value grid as a case file, with the fields where the values would be. It is the
  drawer's own vocabulary rather than a generic centred login box.

Interactive controls use consistent default, hover, focus-visible, disabled, and busy feedback
where each state applies. Buttons use a consistent 36px minimum height and a muted purple focus
mark. Loading uses skeletons; empty states explain the next useful action. Search can be cleared
with an accessible control, and stale search/detail responses cannot replace newer selections.
Skeletons, not spinners. Empty states teach the interface rather than announcing emptiness.

## Motion

State transitions use 170ms exponential ease-out. The authored moment is the card lifting out
of the drawer. The running agent node and loading skeletons pulse on a 1.1s loop because they
show ongoing work. All three effects are disabled under `prefers-reduced-motion`.

## Browser surfaces

Themed, not left at browser defaults: `::selection` is stamp violet on white, `caret-color` is
`--stamp-lit`, scrollbars are cabinet-coloured with a transparent track, `:focus-visible` is a
2px `--stamp-lit` ring at 2px offset, and the select chevron is an inline SVG in `--cab-ink-3`.

## Icons

Five authored inline SVG symbols (search, chevron, run, plus, refresh) at a 16px box, 1.6
stroke, round caps. No icon font, no emoji, no Unicode glyphs standing in for icons.

## Responsive

Structural, not fluid. Below 900px the cabinet stops being two columns: the drawer takes the
full width and caps at 46vh, the sheet follows beneath it, the stamp stops stretching, the
footer drops its keyboard hints and keeps the connection state, and the route scrolls
horizontally rather than crushing its stations.

## Keyboard

`j` / `k` move through the drawer and open as they go, `/` focuses search, `r` runs an
investigation on the open case, `Escape` leaves a field. The footer prints the shortcuts.
