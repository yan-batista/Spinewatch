---
name: Spinewatch
description: One square of vermilion washi, creased into a dated record.
colors:
  vermilion: "#d83c2e"
  vermilion-deep: "#c3301f"
  vermilion-ink: "#a3271b"
  vermilion-wash: "#e07a6e"
  vermilion-tint: "#f6e2de"
  gold-leaf: "#f0dc9a"
  gold-ink: "#a8842a"
  paper: "#f7f3ee"
  paper-plate: "#fffdf9"
  paper-sunk: "#ece7df"
  paper-grey: "#e6e2da"
  sumi: "#1a1a1a"
  sumi-soft: "#635e56"
  sumi-faint: "#8a857c"
  crease: "rgba(26, 26, 26, 0.13)"
  crease-firm: "rgba(26, 26, 26, 0.26)"
  crease-verm: "rgba(163, 39, 27, 0.32)"
  crease-oxblood: "rgba(142, 32, 24, 0.4)"
  ink-ochre: "#7d5710"
  ink-sienna: "#a34a1f"
  ink-oxblood: "#8e2018"
  dye-1: "#1a1a1a"
  dye-2: "#d83c2e"
  dye-3: "#27476b"
  dye-4: "#8c5a2b"
  dye-5: "#6b4368"
  dye-6: "#5f7333"
  dye-7: "#456670"
  dye-8: "#9e3b4e"
  dye-other: "#8a857c"
typography:
  figure:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 300
    lineHeight: 1
    letterSpacing: "-0.015em"
    fontFeature: "tabular-nums lining-nums"
  head:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.15
  lede:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.55
  fine:
    fontFamily: "Spline Sans Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    fontFeature: "tabular-nums"
  label:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.04em"
  mark:
    fontFamily: "Source Sans 3, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.14em"
rounded:
  sharp: "2px"
  soft: "4px"
  disc: "50%"
spacing:
  s1: "0.25rem"
  s2: "0.5rem"
  s3: "0.75rem"
  s4: "1rem"
  s5: "1.5rem"
  s6: "2rem"
  s7: "3rem"
  s8: "4.5rem"
components:
  btn:
    backgroundColor: "{colors.paper-plate}"
    textColor: "{colors.sumi}"
    typography: "{typography.label}"
    rounded: "{rounded.soft}"
    padding: "0.5rem 1rem"
  btn-primary:
    backgroundColor: "{colors.vermilion}"
    textColor: "#ffffff"
    typography: "{typography.label}"
    rounded: "{rounded.soft}"
    padding: "0.5rem 1rem"
  btn-quiet:
    backgroundColor: "{colors.paper-plate}"
    textColor: "{colors.vermilion-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.soft}"
    padding: "0.5rem 1rem"
  btn-danger:
    backgroundColor: "transparent"
    textColor: "{colors.ink-oxblood}"
    typography: "{typography.label}"
    rounded: "{rounded.soft}"
    padding: "0.5rem 1rem"
  input:
    backgroundColor: "{colors.paper-plate}"
    textColor: "{colors.sumi}"
    typography: "{typography.body}"
    rounded: "{rounded.sharp}"
    padding: "0.5rem 0.75rem"
  plate:
    backgroundColor: "{colors.paper-plate}"
    textColor: "{colors.sumi}"
    rounded: "{rounded.sharp}"
    padding: "1.5rem"
  masthead:
    backgroundColor: "{colors.vermilion-deep}"
    textColor: "{colors.paper}"
    padding: "1.5rem 2rem"
  nav-btn:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    padding: "0.25rem 0"
  rubric-title:
    backgroundColor: "transparent"
    textColor: "{colors.vermilion-ink}"
    typography: "{typography.mark}"
  step-dot:
    backgroundColor: "{colors.gold-ink}"
    rounded: "{rounded.disc}"
    size: "0.5rem"
---

# Design System: Spinewatch

## Overview

**Creative North Star: "Orizuru Sequence"**

Spinewatch is one uncut square of vermilion washi, creased into a dated record. The world comes from origami instruction: a single sheet that becomes something through numbered, deliberate folds, where every earlier crease stays visible in the finished form. That is what a price history is — a catalogue read every morning as a sequence of folds, not a wall of tiles.

The refusal is explicit: **there is no card grid**. The catalogue is a continuous ruled register down one sheet, and hairline creases do all the dividing that boxes would otherwise do. Space is the structure. The page is mostly unfilled on purpose, because a sheet with a wide margin is the difference between a document and a dashboard.

Colour is committed rather than sprinkled: vermilion owns the masthead as a whole field, and everything below it is paper, sumi ink, and creases. Gold appears exactly once per context — on the step you are on — and nowhere else. Depth is paper lifting a millimetre off paper, never a floating card.

**Key Characteristics:**
- One field of vermilion; the rest is washi paper and sumi ink
- Hairline creases divide; boxes and cards do not exist
- A numbered margin column, with a gold dot marking only the live step
- Every name carries a small tracked-caps or mono second script beneath it
- The unit is demoted from the magnitude; figures are large, light, and tabular
- Motion is state feedback only, at one duration and one curve

## Colors

A vermilion ground, a paper ground, and sumi ink — plus two reserved languages that never mix with the brand: annotation inks for status, and dye colours for the trace.

### Primary
- **Vermilion** (`#d83c2e`): the primary action fill. White on it clears 4.5:1. It is a fill, never body text.
- **Vermilion Deep** (`#c3301f`): the masthead band, the one region colour owns outright, and the primary button's hover. Washi on it clears 5:1.
- **Vermilion Ink** (`#a3271b`): vermilion *as text* — rubric titles, field marks, quiet-button labels. The only vermilion allowed to carry letterforms on paper.
- **Vermilion Wash / Tint** (`#e07a6e`, `#f6e2de`): the tint is the hover fill for quiet and danger buttons and the error notice ground.

### Secondary
- **Gold Leaf** (`#f0dc9a`): gold as it reads on vermilion — the masthead dot and the active nav underline.
- **Gold Ink** (`#a8842a`): gold as it reads on paper — the live step dot. Two grades because gold genuinely changes value against a red ground versus a white one.

### Neutral
- **Paper** (`#f7f3ee`): the sheet. The page ground.
- **Paper Plate** (`#fffdf9`): a plate laid on the sheet — the detail panels and inputs.
- **Paper Sunk / Grey** (`#ece7df`, `#e6e2da`): the recessed step, used for the notice ground, switch track, and loading blanks.
- **Sumi** (`#1a1a1a`): body ink, 15.75:1 on paper.
- **Sumi Soft** (`#635e56`) and **Sumi Faint** (`#8a857c`): annotation grades for labels, dates, and marks.
- **Crease** (`rgba(26,26,26,0.13)`) and **Crease Firm** (`rgba(26,26,26,0.26)`): the only dividers in the system. Alpha-based so they tint with whatever they cross.

### Tertiary
- **Annotation inks** — **Ochre** (`#7d5710`) for `not_found`, **Sienna** (`#a34a1f`) for `blocked` and `parse_error`, **Oxblood** (`#8e2018`) for `error`. All clear 4.5:1 on both paper grounds. `ok` and `unavailable` take soft sumi: they are facts, not alarms.
- **Dye series** — sumi, shu, ai, kuchiba, murasaki, matcha, tetsu, enji, then a grey for overflow. Traditional dye colours, native to this world, all clearing 3:1 for a 2px stroke.

### Named Rules

**The Ground Rule.** Vermilion is a ground, not an ink. `#d83c2e` fails 4.5:1 as text on paper, so text-weight vermilion is always Vermilion Ink. A paragraph, a table cell, or a body sentence in vermilion is a defect.

**The One Gold Rule.** Gold marks the step you are on and nothing else — the live entry, the latest observation, the current view. The moment gold decorates a second idea it stops meaning "here".

**The Reserved Languages Rule.** Brand colour, status ink, and dye series are three separate vocabularies. Status never borrows vermilion; the trace never borrows the accent to mean "primary". A reader must be able to tell a brand mark from a severity from a series without context.

## Typography

**Body / display Font:** Source Sans 3 (self-hosted woff2, weights 300–700)
**Machine Font:** Spline Sans Mono (self-hosted woff2, weights 400–600)

**Character:** One quiet humanist sans does every human-facing job — the world's grammar calls for "quiet humanist sans beside kanji step names", and the second script here is the machine identifier, not another language. Both faces are self-hosted latin subsets; the page makes no external font request and there is no build step. Nothing in the system is set in a system-default stack.

### Hierarchy
- **Figure** (300, 2.125rem, tabular lining): the price. Large and *light* — weight would make a wall of numbers shout; size alone gives it rank.
- **Head** (600, 1.75rem): view titles, and the masthead wordmark at 0.06em tracking, uppercase.
- **Title** (600, 1.375rem): a register entry's book title.
- **Lede** (400, 1.0625rem) and **Body** (400, 0.9375rem, line-height 1.55): running text and table cells, capped at 62ch.
- **Fine** (mono, 0.8125rem): ISBNs, store slugs, URLs, ISO dates — everything a machine wrote.
- **Label** (600, 0.75rem, 0.04em): buttons and controls.
- **Mark** (600, 0.6875rem, 0.14em, uppercase): rubric titles, field labels, state marks, the unit beside a figure. The smallest voice, and the one that appears most.

### Named Rules

**The Second Script Rule.** Every name carries a smaller, tracked companion beneath or beside it — a title over its ISBN, a figure beside its unit, a rubric over its count. The pairing is the world's kanji-and-romaji relationship, translated: the human name and the machine one, always together, never the same size.

**The Demoted Unit Rule.** Currency is set in Mark and the magnitude in Figure. `BRL` is never the same size as the number it qualifies — the reader is scanning for the quantity, and the unit is a constant.

**The Machine Voice Rule.** Anything a machine produced — slug, ISBN, URL, ISO date, sequence number — is mono with tabular figures. Anything a person reads as language is the sans. Mono is never used to make prose look technical.

## Layout

One centred column at 1140px maximum, on a page ground with wide unfilled margins. The masthead alone is full-bleed: it is the vermilion square the rest is folded from.

The catalogue is a **register**, not a grid — a two-column structure of a 3.5rem numbered margin beside the entry body, with entries separated by a single hairline. Within an entry, listing lines are a three-column grid (store, date, value) separated by *dashed* creases, so a fold inside an entry reads lighter than the fold between entries.

Detail and stores content sits on **plates**: paper-plate surfaces with a hairline border and a 1px lift. A plate is a sheet laid on the sheet, not a card — it has no heavy border, no radius beyond 2px, and never nests inside another plate.

The trace is capped at 46rem and centred, at roughly 1:0.62 — square-ish and centred like the diagrams in a fold sequence, rather than a full-width strip.

Rhythm runs on an eight-step scale from 0.25rem to 4.5rem, with more space above a heading than below it.

Responsive behaviour has two steps, 860px and 640px, and it folds rather than discards: the register's margin column narrows and its index turns horizontal, listing lines restack so the figure keeps its own column, tables compact to the mono grades, and the price and its status are the last things allowed to leave the screen.

### Named Rules

**The No Card Rule.** Nothing in this system is a card. The catalogue is a continuous register divided by creases; detail content sits on plates that never nest. If a surface needs a border, a shadow, and a radius to be understood, the layout underneath it has failed.

**The Wide Margin Rule.** The sheet is mostly unfilled. Content reaches for the measure, not the viewport, and whitespace is structure rather than leftover.

## Elevation & Depth

Paper lifting off paper. There are exactly two elevations: a **plate** at `0 1px 2px rgba(26,26,26,0.045)` — barely a millimetre, enough to read as a separate sheet — and a **float** at `0 10px 28px -12px rgba(26,26,26,0.3), 0 2px 6px rgba(26,26,26,0.07)` for the one element genuinely off the page, the trace tooltip.

Everything else expresses depth tonally: the three paper grades (sunk, page, plate) plus creases. Hover never lifts; it shifts a border or tints a ground.

The sheet carries a kozo-fibre texture — an inline SVG turbulence at 2.8% opacity, multiplied over the page and overlaid on the vermilion band. It is material, not decoration: no external request, no image file, and it is the reason the vermilion reads as dyed paper rather than a flat colour swatch.

### Named Rules

**The Two Elevations Rule.** Plate or float, nothing between. A shadow on a button, a table row, or a register entry is a defect.

## Shapes

Paper is cut, not moulded. **2px** on plates, inputs, and small marks; **4px** on buttons; a full disc only on the step dots and the masthead mark. There is no third radius and no pill.

Form language is ruled and rectangular. Creases do the structural work: solid hairlines between register entries and under rubrics, dashed hairlines inside an entry, and a vermilion-tinted hairline under every rubric title and table header.

### Named Rules

**The Two Radii Rule.** 2px, 4px, and the disc. Anything else — including a stray 1px on a knob — is outside the system.

## Components

**Motion.** Every state change transitions over `180ms` (`110ms` for table-row tints) on `cubic-bezier(0.2, 0, 0, 1)`. That is the whole vocabulary: no entrances, no scroll effects, no shimmer on loading blanks. Everything collapses to `0.01ms` under `prefers-reduced-motion`.

### Mark (favicon)
`frontend/icon.svg` — an open book in washi on a vermilion square at 3/32 radius. Two straight-folded page planes, no curve anywhere, separated by a 2.2-unit vermilion gutter.

Three rules hold it together at favicon size. **The gutter is a gap, not a stroke**: a hairline would fall below one device pixel at 16px and blur, while a gap between two solid fills stays crisp at any scale. **Both pages are solid washi** — an opacity step to suggest depth costs contrast against the vermilion and is invisible small. **No gold**: the gold gutter variant was drawn and rejected because gold fills the separating gap, merging the two pages into one blob below 24px; the gutter is structural. It also keeps gold meaning only "the current step", which a favicon is not.

Verified at 128/64/32/24/20/16, blurred, in greyscale, and in both light and dark browser tab strips. Chosen over a bookmark ribbon (thins to a stripe), a shelf of spines (still reads as a bar chart), a single spine (reads as a battery), a flat stack (reads as a list icon), and a front-on open book (reads as a head and shoulders). The square carries its own ground, so no light or dark variant is needed.

### Masthead
The one field of colour: a full-bleed Vermilion Deep band carrying the fibre texture, with the gold dot and the wordmark in tracked uppercase at left, and the views at right. Nav items are Mark-sized tracked caps in washi at 72% opacity; the current view goes to full opacity and grows a gold-leaf underline that scales in from the left.

### Buttons
- **Shape:** 4px, 1px border, Label type, `0.5rem 1rem`.
- **Primary:** Vermilion fill, white text; hover deepens to Vermilion Deep, active to Vermilion Ink.
- **Quiet:** paper-plate fill with a Crease Verm border and Vermilion Ink text; hover fills with Vermilion Tint. This is the default for navigational actions like "View details".
- **Default:** paper-plate fill, Crease Firm border, sumi text; hover borders in Sumi Soft.
- **Danger:** transparent with a Crease Oxblood border and Oxblood text; hover fills with Vermilion Tint.

### Register Entry
The catalogue's unit. A numbered margin column (`01`, `02`, …) with a step dot — filled Gold Ink when the book is active, a hollow Sumi Faint ring when it is not — beside a body carrying the title, its ISBN in mono, the ruled listing lines, and the action row. State is named in the top-right as a Mark: `Active` in Vermilion Ink, `Disabled` in Sumi Faint. A disabled entry mutes its title and figures but keeps every word at full legibility; it is never dimmed with opacity.

### Listing Line
Store slug in mono, ISO observation date in mono, and the value right-aligned — a figure, a status, or `not crawled yet`. The date is not optional: without it a three-week-old price and this morning's are the same mark on the page.

### Status
A 12px crease mark drawn in SVG plus the status word, in the status ink. The marks come from fold notation: a solid rule for `ok`, a dashed rule for `unavailable`, an open square for `not_found`, a cross for `blocked`, a triangle for `parse_error`, a filled square for `error`. Colour carries severity and shape carries identity, so the vocabulary survives greyscale and colour blindness both.

### Fields and Switch
Inputs are paper-plate at 2px with a Crease Firm border, focusing to Vermilion Ink. Labels sit above in Mark caps. The switch is a real checkbox behind a 2.2rem rectangular track — square, like a folded flap — filling Vermilion when on, with the label naming the control and never the state.

### Plate and Sheet
Plates hold detail content. Tables inside them use Mark-caps headers in Vermilion Ink over a Crease Verm rule, sticky within a capped scroll region, with mono dates and slugs, right-aligned tabular prices, and rows that tint on hover. The history table carries its own numbered sequence column with the gold dot on the most recent reading.

### Trace
A hand-rolled inline SVG, sized from its container so one unit is one CSS pixel. Dye-coloured 2px polylines with round caps, 4px end dots haloed in paper-plate, horizontal creases only for gridlines, mono axis ticks, and end labels above 480px. The crosshair is a dashed Sumi Faint rule; the tooltip is the system's only floating surface. The whole SVG is focusable and arrow-key navigable.

### Loading Blanks
Three creased blanks in the register's own two-column shape, bars in Paper Sunk at 70/30/45%. Static — no shimmer, because this system has no decorative motion.

## Do's and Don'ts

### Do:
- **Do** keep vermilion as a ground and use Vermilion Ink whenever it must carry letterforms.
- **Do** reserve gold for the step you are on — the live entry, the latest reading, the current view.
- **Do** divide with creases: solid between entries, dashed within one.
- **Do** pair every name with its machine identifier in mono beneath or beside it.
- **Do** set the unit in Mark caps and the magnitude in Figure.
- **Do** print the observation date next to every current price.
- **Do** give every status both a colour and a distinct crease mark.
- **Do** keep the sheet mostly unfilled; reach for the measure, not the viewport.
- **Do** hold status inks to 4.5:1 on both paper grounds and dye colours to 3:1.
- **Do** transition state changes at 180ms on the one curve, and let nothing else move.

### Don't:
- **Don't** build a card grid, a KPI tile row, or a sidebar shell. The catalogue is a register. *(The refused arrangement, named in the direction contract.)*
- **Don't** put a shadow on anything that is not a plate or the tooltip.
- **Don't** introduce a third radius or a pill.
- **Don't** let status, dye, and brand colour borrow from each other.
- **Don't** dim a disabled record with opacity — mute its ink and keep its explanation readable.
- **Don't** render a missing or failed price as `—` or `0`; the price cell is empty and the status column carries the reason.
- **Don't** set body copy, table cells, or prose in mono, or use mono to make something look technical.
- **Don't** add a webfont request — both faces are self-hosted latin subsets and the page must make no external call.
- **Don't** animate anything that is not reporting a state change.
