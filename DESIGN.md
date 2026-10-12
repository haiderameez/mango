# Design

<!-- impeccable:design-schema 1 -->

The Mango console is **The Catalogue Drawer**: the incident register is a steel drawer of
typed cards, not a table of rows. A case lifts clear of the drawer to be read. Written from
the built surface at `backend/app/static/console.html`.

## Color

Two grounds, and they mean different things. The **cabinet** is the application chrome —
cold, dark, for a night shift on a second monitor. The **card** is the document plane: every
fact the product asserts sits on card stock. Nothing is on card stock that is not a record.

| Token | Value | Role |
|---|---|---|
| `--cab` / `--cab-2` / `--cab-3` | `#232825` `#2a2f2c` `#313733` | drawer, rail, selected row |
| `--rule` / `--rule-soft` | `#39403c` `#303633` | hairlines in the cabinet |
| `--cab-ink` / `-2` / `-3` | `#c9cfc9` `#aab2ac` `#9ba39d` | text on the cabinet |
| `--card` / `--card-2` / `--card-3` | `#dedbd0` `#d9d5c9` `#c8c3b4` | card stock, block heads, rules |
| `--panel` | `#e7e4da` | recessed panels inside a card |
| `--ink` / `-2` / `-3` | `#3b3626` `#55503b` `#5a5540` | typed ink |
| `--stamp` / `--stamp-lit` | `#5e3f9c` `#a899d9` | **the only accent**: stamps and actions |
| `--seal` | `#15652f` | the resolved seal |

Severity is **data colour and may never be used for identity**: `--sev-low #3d4b56`,
`--sev-medium #7a5007`, `--sev-high #9a360b`, `--sev-critical #871313`. This is why the accent
is violet stamp ink: amber and red were already spoken for, so a warm brand colour would have
collided head-on with the thing the operator most needs to read.

**The palette is deliberately low-contrast.** The cabinet-to-card jump is 10.8:1 and body ink
sits at 8.7:1, down from 13.4 and 14.4 in the first build: warm dark grey on muted greige
rather than black on bone, for a surface someone reads for hours at night. Severity chips are
tinted rather than filled — the hue carries the meaning and the thin tab guide in the drawer
carries the strong signal, so the chips do not have to shout.

Softening stops at legibility. Every foreground/background pair was measured, not estimated,
and the floor is still WCAG AA; the lowest shipped pair is `--cab-ink-3` on `--cab-3` at
4.71:1. Going quieter than this means going below AA, which is a decision to take knowingly.

## Typography

Two families, each doing a job the other cannot:

- **Archivo** — the cabinet's engraved labels, headings, buttons, prose.
- **Courier Prime** — anything typed or measured: case numbers, timestamps, durations, log
  messages, field values, exhibit identifiers. The card stock is typewritten, so monospace
  here is the material, not a costume for "technical".

Fixed rem-free pixel ramp, no fluid clamps: 44px case number, 20px case title, 14.5px probable
cause, 13.5px body, 12.5px typed values, 11px legends. **11px is the hard floor for any
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

Hairline rules and boxes inside boxes do the work that cards and shadows usually do. Every
rule is 1px; the 2px near-black borders under the case header and around the probable cause
were the loudest lines on the page and are gone. There is exactly one shadow in the system —
under the lifted sheet, offset and softly blurred, because the card is physically above the
drawer.

- **`.cardrow`** — a card on edge: severity tab, case number in the margin, title, status,
  timestamp. Packed edge to edge with a hairline between, no gaps and no radius, because cards
  in a drawer touch. `aria-current` marks the open one.
- **`.guide`** — a sticky tab guide dividing the drawer by severity, standing proud of the pack.
- **`.sheet`** — the lifted card. Animates once, 170ms exponential ease-out, respecting
  `prefers-reduced-motion`.
- **`.stamp`** — status, rotated −1.5°, hairline border, in ink / stamp violet / seal green /
  critical red. A resolved case is stamped, never removed; a failed run is stamped and stays
  in the record.
- **`.sev` / `.lvl`** — severity and log level as tinted chips: the colour at 13% behind its
  own darker text, outlined at 34%. Never a filled block.
- **`.rows`** — the ruled label/value grid, 11px tracked-caps label against typed value.
- **`.route`** — the five agents as a route with interchange nodes: filled when done, pulsing
  when running, red when failed, each carrying its own duration.
- **`.exhibit`** — a numbered log record with level, endpoint, timestamp and its context
  fields as chips. Citations in the diagnosis light the matching exhibit.
- **`.cite`** — an exhibit reference. Clicking it scrolls to the exhibit and outlines it.
- **`.ticket`** — the sign-in surface, written as a reader's ticket: the same ruled
  label/value grid as a case file, with the fields where the values would be. It is the
  drawer's own vocabulary rather than a generic centred login box.

Everything interactive has default, hover, focus-visible, disabled and loading. Buttons invert
on hover (ink fills, card-coloured text). Skeletons, not spinners. Empty states teach the
interface rather than announcing emptiness.

## Motion

150–250ms, exponential ease-out, state only. The authored moment is the card lifting out of
the drawer. The running agent node pulses because it is the one thing on screen that is
genuinely still happening. Everything else is instant. All of it is disabled under
`prefers-reduced-motion`.

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
