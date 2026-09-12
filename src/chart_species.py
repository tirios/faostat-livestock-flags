"""Emit out/charts/species-flags.svg: the five species, sized by animals, split by flag.

The job of this chart is one sentence: 84 per cent of these animals are chickens, and
half of the chickens are numbers nobody in the country counted. A table cannot show that
shape and a picture can, so row HEIGHT carries share of the five-species total and row
WIDTH is always 100 per cent, split by observation flag.

Every number is read from out/numbers.json. Nothing is computed here, so the chart and
the prose cannot drift apart: check_numbers.py already gates the prose against that file.

PALETTE NOTE. These are the map's four flag colours, unchanged, because a reader who
scrolls from this chart to the map must not meet a different colour meaning the same
thing. Run against the dataviz validator, that palette returns:

    [FAIL] Lightness band     #1E1B2E L 0.235 and #FFB020 L 0.813 sit outside [0.43, 0.77]
    [FAIL] Chroma floor       #1E1B2E C 0.036 reads as grey
    [PASS] CVD separation     worst adjacent pair dE 15.1 protan, target >= 8
    [PASS] Normal vision      worst adjacent pair dE 27.0, floor 15
    [WARN] Contrast vs surface #FFB020 1.83:1 and #17A88A 3.00:1, relief required

The two failures are band and chroma, not discriminability: the checks that decide
whether a reader can tell the categories apart both pass with margin. Official is
near-black on the map on purpose, since it is the anchor of that design, and lifting it
to L 0.43 would turn it mid-purple there. The contrast warning is discharged the way the
skill requires, with visible labels and a table of the same numbers beside the figure,
and every segment also carries the map's texture, so identity never rests on colour alone.

The two contrast figures were 1.59 and 2.61 on the retired #F4EFE4 ground and are
measured above on the white one; the two failures are properties of the palette and do
not move with the surface.

SKIN NOTE. The frame is TP-Professional: white ground, Schibsted Grotesk, JetBrains Mono
on every machine-reported number, square corners on the legend swatches. Colour belongs
to the data, so the four fills, the textures, the row heights, the row widths and the
in-bar percentages are exactly what they were. Everything here is an attribute on the
element it styles rather than a <style> block, so the post's PNG export path, which
serialises the element, still sees all of it.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUMBERS = ROOT / 'out' / 'numbers.json'
OUT = ROOT / 'out' / 'charts' / 'species-flags.svg'

GROUND = '#FFFFFF'
INK = '#1E1B2E'
MUTED = '#5A6167'

FONT = 'Schibsted Grotesk, system-ui, sans-serif'
MONO = 'JetBrains Mono, monospace'

# Same four as src/interactive_map.py. See the palette note in the module docstring.
COLOURS = {'A': INK, 'E': '#6B7BF0', 'I': '#FFB020', 'X': '#17A88A'}
TEXTURE = {'A': 'solid', 'E': 'dots', 'I': 'diag', 'X': 'cross'}
NAMES = {
    'A': 'Official national figure',
    'E': 'Country estimate',
    'I': 'FAO imputed',
    'X': 'External organisation',
}
# The code letter sits on the swatch, the same idiom as the map's legend and tooltip.
# White reads on the two dark fills, ink on the two light ones.
LETTER_INK = {'A': '#FFFFFF', 'E': '#FFFFFF', 'I': INK, 'X': INK}
ORDER = ['A', 'E', 'I', 'X']

W = 900
GUTTER = 104           # left column for species name and head count
PAD_R = 16
LEGEND_H = 54          # two rows of four 20-unit swatches, from y 6 to y 54
BARS_DY = 26           # the bars group clears the taller legend by this much
STACK_H = 430
ROW_GAP = 3            # surface gap between rows
SEG_GAP = 2            # surface gap between segments
FOOT_H = 56            # two mono footnote lines
H = LEGEND_H + BARS_DY + STACK_H + FOOT_H

# Legend grid: four cells, two per row, at a fixed x rather than packed by label width.
LEG_Y = 6
LEG_COL = (GUTTER, 400)
LEG_ROW_H = 28
SWATCH_SIZE = 20

# The tall row carries three gutter lines: name, head count, share. BIG_NAME_DY places
# the first baseline against the row's centre and the other two follow at BIG_LINE.
BIG_LINE = 20
BIG_NAME_DY = -3.4


def esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def patterns() -> str:
    """Texture defs at a fixed screen scale. The chart never zooms, so unlike the map
    these need no counter-scaling."""
    p = []
    p.append(
        '<pattern id="cdots" width="6" height="6" patternUnits="userSpaceOnUse">'
        f'<rect width="6" height="6" fill="{COLOURS["E"]}"/>'
        '<circle cx="3" cy="3" r="1.15" fill="#FFFFFF" fill-opacity=".55"/></pattern>')
    p.append(
        '<pattern id="cdiag" width="7" height="7" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        f'<rect width="7" height="7" fill="{COLOURS["I"]}"/>'
        '<rect width="2.2" height="7" fill="#FFFFFF" fill-opacity=".5"/></pattern>')
    p.append(
        '<pattern id="ccross" width="7" height="7" patternUnits="userSpaceOnUse">'
        f'<rect width="7" height="7" fill="{COLOURS["X"]}"/>'
        '<path d="M0 3.5h7M3.5 0v7" stroke="#FFFFFF" stroke-opacity=".45" '
        'stroke-width="1.3"/></pattern>')
    return '<defs>' + ''.join(p) + '</defs>'


FILL = {'A': COLOURS['A'], 'E': 'url(#cdots)', 'I': 'url(#cdiag)', 'X': 'url(#ccross)'}
SWATCH = {'A': COLOURS['A'], 'E': 'url(#cdots)', 'I': 'url(#cdiag)', 'X': 'url(#ccross)'}


def build() -> str:
    n = json.loads(NUMBERS.read_text(encoding='utf-8'))
    year = n['headline']['year']
    species = sorted(
        n['by_species'].items(),
        key=lambda kv: -kv[1]['share_of_set_pct'],
    )

    shares = [v['share_of_set_pct'] for _, v in species]
    assert abs(sum(shares) - 100) < 0.4, f'species shares sum to {sum(shares)}, not 100'

    plot_w = W - GUTTER - PAD_R
    usable = STACK_H - ROW_GAP * (len(species) - 1)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="100%" role="img" aria-label="Farmed animals in {year} by species and '
        f'the provenance flag on each country figure" font-family="{FONT}">',
        patterns(),
        f'<rect width="{W}" height="{H}" fill="{GROUND}"/>',
    ]

    # Legend. Always present, and the texture means identity is never colour alone.
    # Two rows of four so each cell can hold a 20-unit swatch with its code letter.
    out.append(f'<g transform="translate(0,{LEG_Y})">')
    for i, f in enumerate(ORDER):
        x = LEG_COL[i % 2]
        ry = (i // 2) * LEG_ROW_H
        ty = ry + 15
        out.append(
            f'<rect x="{x}" y="{ry}" width="{SWATCH_SIZE}" height="{SWATCH_SIZE}" '
            f'fill="{SWATCH[f]}"/>')
        out.append(
            f'<text x="{x + SWATCH_SIZE // 2}" y="{ty}" text-anchor="middle" '
            f'font-size="16" font-weight="600" fill="{LETTER_INK[f]}">{f}</text>')
        out.append(
            f'<text x="{x + SWATCH_SIZE + 8}" y="{ty}" font-size="18" fill="{INK}">'
            f'{esc(NAMES[f])}</text>')
    out.append('</g>')

    out.append(f'<g transform="translate(0,{BARS_DY})">')
    y = LEGEND_H
    for name, v in species:
        share = v['share_of_set_pct']
        row_h = usable * share / 100
        split = v['flag_pct_by_head']
        big = row_h >= 26          # is there room to label inside the row?

        # Species name and head count in the gutter, vertically centred on the row.
        # A short row cannot hold a stack of text: at 3.2 per cent of the animals the
        # pigs row is about 13 px tall, so a second line lands on its neighbour. Those
        # four rows carry the name alone; the 92-unit gutter cannot hold a legible name
        # and its share at this size, and the table under the figure states the share.
        cy = y + row_h / 2
        if big:
            top = cy + BIG_NAME_DY
            out.append(
                f'<text x="{GUTTER - 12}" y="{top:.1f}" text-anchor="end" '
                f'font-size="20" font-weight="800" fill="{INK}">{esc(name)}</text>')
            out.append(
                f'<text x="{GUTTER - 12}" y="{top + BIG_LINE:.1f}" text-anchor="end" '
                f'font-size="17" font-family="{MONO}" fill="{MUTED}">'
                f'{v["head_billions"]:.2f} bn</text>')
            out.append(
                f'<text x="{GUTTER - 12}" y="{top + BIG_LINE * 2:.1f}" '
                f'text-anchor="end" font-size="17" font-family="{MONO}" '
                f'fill="{MUTED}">{share:.1f}%</text>')
        else:
            out.append(
                f'<text x="{GUTTER - 12}" y="{cy + 3.2:.1f}" text-anchor="end" '
                f'font-size="16" fill="{INK}">'
                f'<tspan font-weight="800">{esc(name)}</tspan></text>')

        sx = GUTTER
        for f in ORDER:
            pct = split[f]
            if pct <= 0:
                continue
            seg_w = plot_w * pct / 100
            draw_w = max(seg_w - SEG_GAP, 0.8)
            out.append(
                f'<rect x="{sx:.1f}" y="{y:.1f}" width="{draw_w:.1f}" '
                f'height="{row_h:.1f}" rx="{min(3, row_h / 3):.1f}" fill="{FILL[f]}">'
                f'<title>{esc(name)}: {pct:.1f}% {esc(NAMES[f].lower())}</title></rect>')
            # Label inside only where the block is genuinely big enough to hold it.
            if big and seg_w > 54:
                # White reads on the two dark fills and is marginal on the two light
                # ones, which is exactly the contrast warning the validator raised.
                ink_label = f in ('I', 'X')
                out.append(
                    f'<text x="{sx + seg_w / 2 - SEG_GAP / 2:.1f}" '
                    f'y="{y + row_h / 2 + 5:.1f}" text-anchor="middle" font-size="22" '
                    f'font-weight="700" fill="{INK if ink_label else "#FFFFFF"}">'
                    f'{pct:.0f}%</text>')
            sx += seg_w
        y += row_h + ROW_GAP
    out.append('</g>')

    # Footnote, two mono lines below the bars group. Same words as the single line it
    # replaces; the machine-reported figures put it in the mono face.
    foot = [
        f'Row height is the share of all '
        f'{n["headline"]["total_head_millions"] / 1000:.1f} billion animals',
        f'Row width is always 100 per cent &#183; FAOSTAT {year}',
    ]
    for i, line in enumerate(foot):
        out.append(
            f'<text x="{GUTTER}" y="{H - 28 + i * 22}" font-size="17" '
            f'font-family="{MONO}" fill="{MUTED}" letter-spacing=".04em">'
            f'{line.upper()}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    svg = build()
    OUT.write_text(svg, encoding='utf-8', newline='\n')
    n = json.loads(NUMBERS.read_text(encoding='utf-8'))
    for name, v in n['by_species'].items():
        s = v['flag_pct_by_head']
        print(f'  {name:9s} {v["share_of_set_pct"]:5.1f}% of animals   '
              f'A {s["A"]:5.1f}  E {s["E"]:5.1f}  I {s["I"]:5.1f}  X {s["X"]:5.1f}')
    print(f'wrote {OUT.relative_to(ROOT)}  ({len(svg) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
