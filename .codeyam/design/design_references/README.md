# Design References

This folder ships with every new CodeYam project as
`.codeyam/design/design_references/`. It is a **reading library**, not a
catalog of things to apply. Its 74 documents are reverse-engineered analyses
of how well-known products actually build their interfaces: the real hex
values, the real type scales, the real spacing rhythm, the real component
anatomy.

Vendored from [voltagent/awesome-design-md](https://github.com/voltagent/awesome-design-md)
(MIT). Fetched 2026-09-23. Each file is `design-md/<brand>/DESIGN.md` upstream,
renamed to `<brand>.md` here and otherwise byte-faithful, so a re-vendor is a
re-download rather than a merge.

## How this differs from `design_systems/`

| | `design_systems/` | `design_references/` (this folder) |
|---|---|---|
| What it is | 20 original design languages authored for CodeYam | 74 analyses of existing products |
| Can be applied faithfully | Yes, that is what they are for | **No.** See below |
| Ships fonts | Yes, `<system>.fonts.css` | No |
| Ships example screens | Some, `<system>-example-*.html` | No |
| Names a real company | No | Yes, and that is the whole problem |

## The rule that makes this folder safe to use

**A reference is never applied as a skin.** Shipping a product that reads as
Stripe's or Apple's interface with different words in it is not a design, it is
a costume, and the user did not ask for a costume. It is also the failure mode
this folder most invites, because every file here is a complete, coherent,
ready-to-copy system.

So: take *technique*, leave *identity*.

- **Take** the craft. How does Linear get density without clutter? How does
  Nike build typographic contrast? How does Stripe treat numerics? Those
  answers are transferable and they are why this folder exists.
- **Leave** the tokens. The palette, the typeface, the logo geometry, and the
  signature motif belong to that company. A slot that draws on a reference
  re-derives its own palette and type from the user's brief and assets.

The practical test: if someone who knows the referenced product could name it
from the mockup, the slot took identity, not technique. Redo it.

## When a reference may anchor a slot

The `codeyam-design` skill treats these documents and the `design_systems/`
catalog as one pool of candidates, gated on a genuine match against the brief
(see that skill's Step 2). A reference passes the gate on *structural* fit: the
brief's surface, density, and information shape line up with what that document
describes. "It looks nice" is not a match, and neither is "the user is also a
developer tool."

A reference that passes still gets re-tokenized per the rule above. The
structure may survive; the identity may not.

## File naming

`<brand>.md`, lowercase, matching the upstream directory name (`linear.app.md`,
`bmw-m.md`, `dell-1996.md`). The stem is the reference *id*. Mockups never take
a reference id in their filename: a slot built off a reference is off-catalog by
definition, because it carries no catalog system. It is named
`NN-offcatalog-mockup.html` like any other bespoke slot, and the Step 4
numbered key names the reference it drew technique from.

## Structure of each document

Upstream's shape, unchanged: YAML frontmatter carrying `name`, a long
`description`, and machine-readable `colors` / `typography` blocks, followed by
`## Overview`, `## Colors`, `## Typography`, `## Layout`, `## Elevation & Depth`,
`## Shapes`, `## Components`, `## Do's and Don'ts`, `## Responsive Behavior`,
`## Iteration Guide`, and `## Known Gaps`.

`## Components` and `## Do's and Don'ts` are the two sections worth reading
closely. They carry the transferable craft. `## Colors` and the frontmatter
token blocks are the sections to read for *method* and never to copy verbatim.
