"""The interactive map: out/map-2022.html, one self-contained file, no server, no library.

Same data as out/map-2022.png, read from the same drawn export (out/map-2022-drawn.csv).
Hover a country, zoom and pan, export a PNG.

Design pass of 2026-09-12 ("TP-Professional"),
replacing the 2026-09-09 "Arcade light" pass. The palette, type and layout are theirs; the
assertions below are the project's and every one of them still runs, though the no-figure
border guard had to be re-aimed and lost margin (see main()). Notes on the pass, including
superseded palettes, are not carried in this repository.

  Projection. Plate carree is the default because a rectangular map is what most readers
  expect, but it is NOT equal-area: it stretches high latitudes, so Russia, Canada and
  Greenland render far larger than their land area. Equal Earth is offered alongside it
  and is the honest one.

  Two variables at once. "Count + flag" puts the head count in the fill and the flag in a
  texture over it, and the texture is the stacked bar chart's mark: a dot for a country
  estimate, a 45 degree bar for an FAO imputation, a cross rule for an external source,
  official left solid. Head count has no meaningful midpoint, so hue
  alone would be a diverging palette on sequential data; the ramp therefore also falls
  monotonically in luminance, 239 to 29, asserted at build time. The count scale is
  logarithmic, one class per decade, rebuilt PER SPECIES from that species' own range.

  Zoom. A texture in a five-pixel polygon is noise, so the map zooms and pans, and it
  reports how many countries are still too small to show their texture at the current
  zoom. That number falls as you zoom in; it is not hidden.

Geometry resolution. Coordinates are emitted to one decimal place, not rounded to whole
units. At W=1600 one whole unit spans 25 km, which at 12x zoom is a 12-pixel staircase
along every coastline: the map looked low-resolution not because the source was coarse but
because the OUTPUT was quantised. One decimal puts that step at 2.5 km. Simplification is
0.02 degrees, about 2.2 km, which is under a pixel at the deepest zoom.

Run: .venv/Scripts/python src/interactive_map.py
Out: out/map-2022.html
"""

import json
import os
import math
import pandas as pd
import geopandas as gpd
from shapely.geometry import MultiPolygon

YEAR = 2022
SPECIES = ['Chickens', 'Cattle', 'Sheep', 'Goats', 'Pigs']

# --- TP-Professional palette ----------------------------------------------------------
# The organising rule is that the interface is achromatic and colour belongs to the data.
# So the chrome moves and the data does not: COLOURS, COUNT_STOPS, TEX_INK_DARK and
# TEX_INK_LIGHT are byte-identical to the stacked bar chart's in the write-up, and a
# reader crossing from the chart to the map never meets a different colour meaning the
# same thing. FLAG_A is deliberately NOT INK: the chrome's text went to #141618, the A
# flag stayed on #1E1B2E, and tying the two together would have dragged the data with it.
FLAG_A = '#1E1B2E'          # the A flag, the ramp's darkest step, and the texture ink
GROUND = '#FFFFFF'          # page, cards, PNG canvas
SEA = '#FFFFFF'             # ocean and page are one surface, so the coastline is the edge
INK = '#141618'
ACCENT = '#0F766E'          # teal: the kicker, focus rings, the live dot, the flag outline
DEEP_ACCENT = '#0A4F49'     # teal press: card kickers, link hover
MUTED = '#5A6167'
HAIRLINE = '#E3E6E8'        # story card border
MID_RULE = '#C4C9CC'        # control outlines, dividers, the no-figure border
WELL = '#EFF1F2'            # the texture key's swatch ground
SHADOW = '0 3px 10px rgba(20,22,24,.12)'   # INK at 12 per cent; overlays only
FONT_SANS = '"Schibsted Grotesk",system-ui,sans-serif'
FONT_MONO = '"JetBrains Mono",ui-monospace,SFMono-Regular,monospace'
SVG_MONO = '"JetBrains Mono",ui-monospace,monospace'
FONT_HREF = ('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600'
             '&family=Schibsted+Grotesk:wght@400;500;600&display=swap')
COLOURS = {'A': FLAG_A, 'E': '#6B7BF0', 'I': '#FFB020', 'X': '#17A88A'}
NOROW = '#ECE7DD'
NOROW_STROKE = MID_RULE
BORDER = '#ffffff'
TEX_INK_DARK = FLAG_A
TEX_INK_LIGHT = '#ffffff'
COUNT_STOPS = ['#FFF1A8', '#FFC15C', '#FF7A59', '#C84E9A', '#7B3FA0', '#3A2A6B', FLAG_A]

# Noun phrases, not sentences: these are legend keys, and "FAO imputed it" reads as a
# narrator's aside rather than as the name of a category.
LABEL = {'A': 'Official national figure', 'E': 'Country estimate',
         'I': 'FAO imputed', 'X': 'External organisation',
         'none': f'No figure for this species in {YEAR}'}
# The texture is the chart's mark: a dot, a 45 degree bar, a cross rule. Official stays
# solid because it is the largest class and marking it would cover most of the map.
TEXTURE = {'A': 'solid', 'E': 'dots', 'I': 'diag', 'X': 'cross'}
TEXTURE_LABEL = {'solid': 'solid', 'dots': 'dots', 'diag': 'diagonal', 'cross': 'cross'}
# Nothing reads GLYPH any more. It is still emitted because the tooltip and the drill
# table name the flag by its code letter and a future mark may want it back.
GLYPH = {'dots': 'E', 'diag': 'I', 'cross': 'X'}

NAME_M49 = {'Norway': '578', 'Taiwan': '158'}
SENTINEL = '-099'

# Simplification tolerance in each CRS's own units, about 2.2 km either way.
PROJECTIONS = {
    'flat': ('EPSG:4326', 0.02, 'Plate carree'),
    'equal': ('+proj=eqearth +lon_0=0 +datum=WGS84 +units=m +no_defs', 2200, 'Equal Earth'),
}
# The companion write-up. The story is the artefact and the post is its backstory, so
# the link goes story -> post and sits in the final chapter, not in the scroll.
# Where the companion write-up lives, if it is being built alongside one. Empty by
# default: this repository holds the pipeline, not the write-up, so the button that
# points at it is omitted rather than left dangling. Set POST_HREF in the environment
# when building the pages that ship next to the write-up.
POST_HREF = os.environ.get('POST_HREF', '')

DEFAULT_PROJ = 'equal'   # Equal Earth. The claim is a share of the world's ANIMALS, so the
                         # default has to preserve area. Note this is not what Our World in
                         # Data uses: their world map is Robinson, centred on Greenwich,
                         # which looks similar and is not equal-area. Both stay available.

W = 1600
# The figure keeps its header in the SVG; the story has none. 620 reserved the 324-unit
# band the three-line SVG headline used to occupy, so the page opened on an empty field
# above the subtitle. 336 seats the kicker, two subtitle lines and the taller legend row.
TOP_FIGURE, BOTTOM = 336, 0
COORD_DP = 1                # decimal places on emitted coordinates, see module docstring

TEXTURE_TILE = 18
# Two texture repeats of TRUE land area. The previous value was calibrated against
# bounding boxes, which overstate every country and badly overstate ragged ones.
TEXTURE_MIN_PX2 = TEXTURE_TILE ** 2


def luminance(hexcolour):
    r, g, b = [int(hexcolour[1 + 2 * i:3 + 2 * i], 16) for i in range(3)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def load_geo():
    """Identical guards to draw_map.py, including the duplicate-M49 assertion that fires on
    the Taiwan-as-Dominican-Republic defect."""
    g = gpd.read_file('data/geo/ne_50m_admin_0_countries.geojson')
    g = g[g['NAME'] != 'Antarctica'].copy()
    g['m49'] = g['UN_A3'].astype(str).str.zfill(3)
    for name, code in NAME_M49.items():
        n = (g['NAME'] == name).sum()
        assert n == 1, f'expected exactly one {name} geometry, found {n}'
        g.loc[g['NAME'] == name, 'm49'] = code
    dup = set(g.loc[g['m49'].duplicated(keep=False), 'm49']) - {SENTINEL}
    assert not dup, f'geometries share an M49 code, one will take the other\'s data: {dup}'
    return g.reset_index(drop=True)


def build_projection(geo4326, crs, tol):
    """Return (paths, height) for one projection, in a 0..W pixel frame."""
    g = geo4326.to_crs(crs)
    g = g.assign(geometry=g.geometry.simplify(tol, preserve_topology=True))
    minx, miny, maxx, maxy = g.total_bounds
    sx = W / (maxx - minx)
    H = (maxy - miny) * sx

    def fmt(v):
        # Trim a trailing '.0' so whole coordinates cost no extra bytes.
        s = f'{v:.{COORD_DP}f}'
        return s[:-2] if s.endswith('.0') else s

    def ring_d(ring):
        """One ring as 'M x y l dx dy dx dy ... Z'.

        Relative deltas rather than absolute coordinates: a coastline step is a small
        number ('1.2 -.7') where the absolute position is a large one ('1042.3 218.6'),
        which roughly halves the bytes at the same precision. The running position is
        advanced by the ROUNDED delta, not the true one, so rounding error cannot
        accumulate along a ring and pull the far end off the coast.
        """
        pts = [((x - minx) * sx, (maxy - y) * sx) for x, y in ring.coords]
        if not pts:
            return ''
        x0, y0 = pts[0]
        cx, cy = round(x0, COORD_DP), round(y0, COORD_DP)
        out = ['M', fmt(x0), ' ', fmt(y0), 'l']
        for x, y in pts[1:]:
            dx, dy = round(x - cx, COORD_DP), round(y - cy, COORD_DP)
            cx += dx
            cy += dy
            out.append(f'{fmt(dx)} {fmt(dy)} ')
        out.append('Z')
        return ''.join(out)

    paths = []
    for i, r in g.iterrows():
        geom = r.geometry
        polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        d = []
        for p in polys:
            if p.is_empty:
                continue
            for ring in [p.exterior, *p.interiors]:
                d.append(ring_d(ring))
        paths.append({'i': int(i), 'm': r['m49'], 'n': r['NAME'], 'd': ''.join(d),
                      'a': round(geom.area * sx * sx, 1)})
    return paths, H


def ramp(n):
    """n colours sampled along COUNT_STOPS by linear interpolation in RGB.

    Luminance is linear in R, G and B, so interpolating between stops that fall in
    luminance yields a ramp that also falls. The caller asserts it anyway.
    """
    if n <= 1:
        return [COUNT_STOPS[-1]]
    out = []
    for k in range(n):
        t = k / (n - 1) * (len(COUNT_STOPS) - 1)
        a, f = int(t), t - int(t)
        c0, c1 = COUNT_STOPS[a], COUNT_STOPS[min(a + 1, len(COUNT_STOPS) - 1)]
        rgb = [round(int(c0[1 + 2 * z:3 + 2 * z], 16) * (1 - f)
                     + int(c1[1 + 2 * z:3 + 2 * z], 16) * f) for z in range(3)]
        out.append('#%02x%02x%02x' % tuple(rgb))
    return out


def main(out='out/map-2022.html', story=False):
    """Build one page. story=False is the embeddable figure, story=True the narrative.

    Both shells share one engine (SCRIPT_CORE); only the chrome, the CSS and a handful of
    branches on the STORY flag differ. Keeping one engine is the point: the assertions, the
    texture rules and the zoom maths cannot drift between the two pages.
    """
    lums = [luminance(c) for c in COUNT_STOPS]
    assert all(lums[i] > lums[i + 1] for i in range(len(lums) - 1)),         f'count ramp is not monotone in luminance: {[round(x) for x in lums]}'

    # The three pale surfaces have collided twice before: sea, no-figure, and the palest
    # count class. Both guards below survived the TP palette change, but the second one
    # had to be re-aimed and that is a real loss of margin, not a tidy-up.
    #
    # Sea against no-figure is still carried by luminance, but the sign flipped: the sea
    # used to be the darker of the two and is now white, so the guard measures distance
    # rather than a signed drop. Threshold unchanged at 20; measured 23.7.
    assert abs(luminance(NOROW) - luminance(SEA)) >= 20,         f'no-figure is too close to the sea: {abs(luminance(NOROW) - luminance(SEA)):.1f} points'
    # The no-figure BORDER is what separates that fill from the sea on one side and from
    # the palest count class on the other. Under the old sand palette it stood 109 points
    # off its own fill and the guard asked for 80. Under TP it stands 31, so an 80-point
    # guard cannot hold. The threshold is now 22, the figure the brief named for the
    # no-figure/palest-class separation the border exists to carry, and it is applied to
    # all three surfaces the border sits between. Margins: fill 31.2, palest class 38.6,
    # sea 54.9. Anything that moves NOROW_STROKE towards any of them trips this.
    for _surface, _name in ((NOROW, 'its own fill'), (COUNT_STOPS[0], 'the palest count class'),
                            (SEA, 'the sea')):
        _sep = abs(luminance(_surface) - luminance(NOROW_STROKE))
        assert _sep >= 22,             f'the no-figure border does the work the fill cannot; it is {_sep:.1f} points from {_name}'

    top = 0 if story else TOP_FIGURE
    geo = load_geo()
    projs = {}
    for key, (crs, tol, label) in PROJECTIONS.items():
        paths, H = build_projection(geo, crs, tol)
        projs[key] = {'label': label, 'paths': paths, 'H': round(H)}
        print(f'  {label:14s} {len(paths)} geometries, height {H:.0f} px, '
              f'{sum(len(p["d"]) for p in paths) // 1024} KB of path data')

    N = json.load(open('out/numbers.json', encoding='utf-8'))
    dr = pd.read_csv('out/map-2022-drawn.csv', dtype={'m49': str, 'ne_un_a3': str})
    dr['m49'] = dr['m49'].str.zfill(3)

    data = {}
    for _, r in dr[dr['m49'] != SENTINEL].iterrows():
        flag = r['rendered_as'] if isinstance(r['rendered_as'], str) else 'none'
        head = None if pd.isna(r['head']) else float(r['head'])
        area = None if pd.isna(r['fao_area']) else r['fao_area']
        data.setdefault(r['m49'], {})[r['species']] = [flag, head, area]

    summary = {}
    for sp in SPECIES:
        s = dr[(dr['species'] == sp) & (dr['fao_area'].notna())]
        tot = s['head'].sum()
        by = {f: {'pct': round(s[s['Flag'] == f]['head'].sum() / tot * 100, 1),
                  'areas': int((s['Flag'] == f).sum())} for f in 'AEIX'}
        none_areas = int(((dr['species'] == sp) & (dr['fao_area'].isna())
                          & (dr['m49'] != SENTINEL)).sum())
        pub = N['by_species'][sp]
        assert by['A']['pct'] == pub['pct_official_by_head'], (sp, by['A']['pct'], pub['pct_official_by_head'])
        assert round(tot / 1e9, 2) == pub['head_billions'], (sp, tot, pub['head_billions'])
        assert len(s) == pub['reporting_areas'], (sp, len(s), pub['reporting_areas'])
        summary[sp] = {'total_head': float(tot), 'head_billions': pub['head_billions'],
                       'reporting_areas': int(len(s)),
                       'pct_official_by_area': pub['pct_official_by_area'],
                       'share_of_set_pct': pub['share_of_set_pct'],
                       'by': by, 'none_areas': none_areas}

        v = s.loc[s['head'].notna() & (s['head'] > 0), 'head']
        lo, hi = math.floor(math.log10(v.min())), math.ceil(math.log10(v.max()))
        edges = [10.0 ** e for e in range(lo, hi + 1)]
        cols = ramp(len(edges) - 1)
        cl = [luminance(c) for c in cols]
        assert all(cl[i] > cl[i + 1] for i in range(len(cl) - 1)), (sp, cl)
        placed = sum(1 for x in v if any(edges[k] <= x < edges[k + 1] for k in range(len(edges) - 1)))
        assert placed == len(v), f'{sp}: {len(v) - placed} of {len(v)} rows fall outside the classes'
        summary[sp]['bins'] = {'edges': edges, 'colours': cols,
                               'lum': [round(x) for x in cl],
                               'min': float(v.min()), 'max': float(v.max())}
        print(f'  {sp:9s} 1e{lo} to 1e{hi}, {len(cols)} classes, all {len(v)} rows placed, '
              f'luminance {round(cl[0])} to {round(cl[-1])}')

    tw = data['158']
    assert tw['Chickens'][0] == 'A' and tw['Cattle'][0] == 'A', tw

    rec, src = N['reconciliation'], N['source']
    # One paragraph, the source and the two things a reader has to know to read the
    # colours correctly. The caveats that used to follow it (the missing states, the
    # revision direction, the projection) live in the write-up, where a reader who
    # wants them is already reading prose. A figure carrying four paragraphs of
    # qualification under it reads as apology rather than as a caption.
    note = [
        f"Source: {src['database']}, release {src['release']}, observation status flags. Standing head counts "
        "for five species, not all farmed animals and not animals slaughtered. In count modes the colour scale is "
        "logarithmic, one class per decade, rebuilt for each species, so colours are not comparable between species.",
    ]

    html = (HEAD
            + (CSS_STORY if story else CSS_FIGURE) + CLOSE_HEAD
            + (BODY_STORY if story else BODY_FIGURE) + OPEN_SCRIPT
            + SCRIPT_CORE + (SCRIPT_STORY if story else '') + BOOT)
    for k, v in {
        '__YEAR__': str(YEAR), '__W__': str(W), '__TOP__': str(top), '__BOTTOM__': str(BOTTOM),
        '__PROJS__': json.dumps(projs, separators=(',', ':')),
        '__DEFAULT_PROJ__': json.dumps(DEFAULT_PROJ),
        '__READMORE__': (
            '      <a class="again readmore" id="readmore" href="' + POST_HREF + '">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="square" aria-hidden="true"><path d="M4 4h11l5 5v11H4zM15 4v5h5'
            'M8 13h8M8 17h5"/></svg>How this was made</a>\n' if POST_HREF else ''),
        '__DATA__': json.dumps(data, separators=(',', ':')),
        '__SUMMARY__': json.dumps(summary, separators=(',', ':')),
        '__SPECIES__': json.dumps(SPECIES), '__COLOURS__': json.dumps(COLOURS),
        '__NOROW__': NOROW, '__NOROW_STROKE__': NOROW_STROKE, '__SEA__': SEA,
        '__GROUND__': GROUND, '__INK__': INK, '__DEEP_ACCENT__': DEEP_ACCENT, '__MUTED__': MUTED,
        '__BORDER__': BORDER, '__TEX_INK_DARK__': TEX_INK_DARK, '__TEX_INK_LIGHT__': TEX_INK_LIGHT,
        '__ACCENT__': ACCENT, '__FLAG_A__': FLAG_A, '__FLAG_I__': COLOURS['I'],
        '__HAIRLINE__': HAIRLINE, '__MID_RULE__': MID_RULE, '__WELL__': WELL, '__SHADOW__': SHADOW,
        '__FONT_SANS__': FONT_SANS, '__FONT_MONO__': FONT_MONO, '__SVG_MONO__': SVG_MONO,
        '__FONT_HREF__': FONT_HREF,
        '__LABEL__': json.dumps(LABEL), '__NOTE__': json.dumps(note),
        '__TEXTURE__': json.dumps(TEXTURE), '__TEXTURE_LABEL__': json.dumps(TEXTURE_LABEL),
        '__GLYPH__': json.dumps(GLYPH),
        '__TEXMIN__': str(TEXTURE_MIN_PX2), '__TILE__': str(TEXTURE_TILE),
        '__IS_STORY__': 'true' if story else 'false',
        '__FLAG_E__': COLOURS['E'], '__FLAG_X__': COLOURS['X'],
    }.items():
        html = html.replace(k, v)

    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    print(f'wrote {out}  ({len(html.encode("utf-8")) / 1024:.0f} KB)')



HEAD = r"""<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Where the world's livestock numbers come from (__YEAR__)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="__FONT_HREF__">
<style>
"""

CLOSE_HEAD = r"""</style>
</head>
<body>
"""

OPEN_SCRIPT = r"""
<script>
"""

BOOT = r"""
buildGeometry(); paint();
</script>
</body>
</html>
"""

# JetBrains Mono carries every machine-reported number and nothing else. A number a human
# typed into prose stays in the sans. Same block on both pages.
CSS_MONO = r"""  /* TP: mono marks machine-reported content */
  .top span,.hint,.zlev,.legend .pct,.legend .ramp .ends,.card .num,.tabs button .k,
  #tip table,#tip .h,.drill table,.drill .src code{font-family:var(--font-mono); font-feature-settings:"tnum";}
  .card .num{letter-spacing:-.04em;}
  .tabs button .k{letter-spacing:-.03em;}
"""

CSS_FIGURE = r"""  :root{
    --color-bg:__GROUND__; --color-text:__INK__; --color-accent:__ACCENT__; --accent-deep:__DEEP_ACCENT__;
    --color-divider:__MID_RULE__;
    --font-heading:__FONT_SANS__; --font-body:__FONT_SANS__; --font-mono:__FONT_MONO__;
    --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-6:24px; --space-8:32px;
    --shadow-md:__SHADOW__;
    --nodata-border:__NOROW_STROKE__;
  }
  html,body{margin:0; background:var(--color-bg); color:var(--color-text); font-family:var(--font-body); font-size:15px; line-height:1.5;}
  .wrap{max-width:1600px; margin:0 auto; padding:0 var(--space-6) var(--space-8);}
  .bar{display:flex; flex-wrap:wrap; align-items:flex-end; gap:var(--space-3) var(--space-8); border-bottom:2px solid var(--color-text);}
  .tabs{display:flex; flex-wrap:wrap; margin-right:auto;}
  .tabs button{font-family:var(--font-heading); font-weight:400; font-size:11px; letter-spacing:.08em; text-transform:uppercase; line-height:1;
    padding:var(--space-4) var(--space-6) var(--space-3) 0; margin-right:var(--space-4); border:0; border-bottom:6px solid transparent; margin-bottom:-2px;
    background:transparent; color:var(--color-text); cursor:pointer; display:flex; flex-direction:column; align-items:flex-start; gap:var(--space-2);
    white-space:nowrap; text-align:left; opacity:.4;}
  .tabs button .k{font-size:clamp(40px,5vw,72px); font-weight:600; letter-spacing:-.04em; line-height:.9; font-variant-numeric:tabular-nums;}
  .tabs button:hover{opacity:.75;}
  .tabs button[aria-pressed="true"]{opacity:1; border-bottom-color:var(--color-text);}
  .grp{display:flex; flex-direction:column; gap:var(--space-1); flex:none; padding-bottom:var(--space-3);}
  .grp>span{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:color-mix(in srgb,var(--color-text) 60%,transparent);}
  .seg{display:inline-flex; border:1px solid var(--color-divider);}
  .seg button{font:inherit; font-size:13px; line-height:1.2; padding:7px var(--space-3); cursor:pointer; border:0; border-left:1px solid var(--color-divider);
    background:transparent; color:var(--color-text); display:inline-flex; align-items:baseline; gap:var(--space-2); text-align:left; white-space:nowrap;}
  .seg button:first-child{border-left:0;}
  .seg button:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);}
  .seg button[aria-pressed="true"]{background:var(--color-text); color:var(--color-bg);}
  button:focus-visible{outline:2px solid var(--color-accent); outline-offset:2px;}
  .btn{font-family:var(--font-heading); font-weight:600; font-size:13px; line-height:1.2; cursor:pointer; padding:var(--space-2) calc(var(--space-3)*1.2);
    border:1px solid var(--color-divider); background:transparent; color:var(--color-text); display:inline-flex; align-items:center; gap:var(--space-2);
    text-align:left; white-space:nowrap; flex:none; align-self:flex-end; margin-bottom:var(--space-3);}
  .btn:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);}
  .btn:active{background:color-mix(in srgb,var(--color-text) 14%,transparent);}
  .btn:disabled{opacity:.45; cursor:not-allowed;}
  .btn svg{display:block; width:14px; height:14px; flex:none;}
  .hint{font-size:13px; color:color-mix(in srgb,var(--color-text) 60%,transparent); margin:var(--space-2) 0 0; min-height:1.5em; font-variant-numeric:tabular-nums;}
  .stage{position:relative; overflow:hidden; background:var(--color-bg);}
  #map{display:block; width:100%; height:auto; touch-action:none;}
  #zoom{cursor:grab;} #zoom.dragging{cursor:grabbing;} #tex{pointer-events:none;}
  #tip{position:absolute; pointer-events:none; display:none; background:var(--color-bg); color:var(--color-text); border:1px solid var(--color-text);
    font-size:13px; line-height:1.45; padding:var(--space-2) var(--space-3); width:max-content; max-width:min(90vw,480px); box-shadow:var(--shadow-md);}
  #tip b{display:block; font-family:var(--font-heading); font-weight:600; font-size:14px; margin-bottom:2px;}
  #tip .f{display:inline-block; width:.75em; height:.75em; margin-right:.4em; vertical-align:-.08em; border:1px solid transparent;}
  #tip .f.n{border-color:var(--nodata-border);}
  #tip table{border-collapse:collapse; margin-top:6px; font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap;}
  #tip th{font-weight:400; font-size:10px; letter-spacing:.08em; text-transform:uppercase; text-align:left; padding:0 10px 2px 0;
    color:color-mix(in srgb,var(--color-text) 60%,transparent); border-bottom:1px solid var(--color-divider);}
  #tip td{padding:4px 10px 0 0; white-space:nowrap;}
  #tip td.flag, #tip th.flag{padding-right:4px; padding-left:6px;}
  #tip td.flag{font-weight:600;}
  #tip td.flag span{display:inline-block; min-width:1.6em; text-align:center; outline:2px solid var(--color-accent); outline-offset:1px;}
  #tip .h{display:block; margin-top:6px; white-space:normal; max-width:28em;
    color:color-mix(in srgb,var(--color-text) 65%,transparent); font-variant-numeric:tabular-nums;}
  .zoomui{position:absolute; right:var(--space-3); bottom:var(--space-3); display:flex; align-items:stretch;
    border:1px solid var(--color-divider); background:var(--color-bg);}
  .zoomui button{font:inherit; font-size:15px; line-height:1; width:32px; height:32px; padding:0; border:0;
    border-left:1px solid var(--color-divider); background:transparent; color:var(--color-text); cursor:pointer;}
  .zoomui button:first-child{border-left:0;}
  .zoomui button:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);}
  .zoomui #zreset{width:auto; font-size:12px; padding:0 var(--space-3);}
  .zlev{font-size:12px; line-height:32px; min-width:3.4em; text-align:center; border-left:1px solid var(--color-divider); font-variant-numeric:tabular-nums;}
  .note{display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:var(--space-4) var(--space-6); margin-top:var(--space-6); padding-top:var(--space-4);
    border-top:2px solid var(--color-text); font-size:13px; line-height:1.5; color:color-mix(in srgb,var(--color-text) 75%,transparent);}
  .note p{margin:0; text-wrap:pretty;}
  .foot{font-size:12px; color:color-mix(in srgb,var(--color-text) 55%,transparent); margin-top:var(--space-6); padding-top:var(--space-3);
    border-top:1px solid var(--color-divider); line-height:1.5; text-wrap:pretty;}
  .foot code{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.92em;}""" + CSS_MONO

CSS_STORY = r"""  :root{
    --color-bg:__GROUND__; --color-text:__INK__; --color-accent:__ACCENT__; --accent-deep:__DEEP_ACCENT__;
    --color-divider:__MID_RULE__;
    --font-heading:__FONT_SANS__; --font-body:__FONT_SANS__; --font-mono:__FONT_MONO__;
    --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-6:24px; --space-8:32px;
    --shadow-md:__SHADOW__;
    --flag-A:__FLAG_A__; --flag-E:__FLAG_E__; --flag-I:__FLAG_I__; --flag-X:__FLAG_X__; --sea:__SEA__; --nodata:__NOROW__; --nodata-border:__NOROW_STROKE__;
  }
  html{scroll-behavior:smooth;}
  html,body{margin:0; background:var(--color-bg); color:var(--color-text); font-family:var(--font-body); font-size:15px; line-height:1.5;}
  body.explore{overflow:hidden;}
  button{font:inherit; color:inherit;}
  button:focus-visible{outline:2px solid var(--color-accent); outline-offset:2px;}
  /* ---- fixed map ---- */
  .stage{position:fixed; inset:0; z-index:0; overflow:hidden; background:__SEA__;}
  #map{display:block; width:100%; height:100%; touch-action:none;}
  #zoom{cursor:grab; transition:transform 1.4s cubic-bezier(.2,.7,.1,1);} #zoom.dragging{cursor:grabbing; transition:none;} #tex{pointer-events:none;}
  .country{transition:opacity .7s;} .country.dim{opacity:.14;} #tex use{transition:opacity .7s;} #tex use.dim{opacity:0;}
  .stage.veil::after{content:""; position:absolute; inset:0; background:linear-gradient(90deg,color-mix(in srgb,var(--color-bg) 88%,transparent) 30%,color-mix(in srgb,var(--color-bg) 35%,transparent) 100%); pointer-events:none; transition:opacity .8s;}
  .stage::after{opacity:0;}
  @keyframes nodata{0%,100%{fill:__NOROW__} 50%{fill:__FLAG_I__}}
  .stage.pulse .country.nodata{animation:nodata 1.6s ease-in-out infinite; stroke:__FLAG_I__;} .stage.veil::after{opacity:1;}
  /* ---- top bar ---- */
  .top{position:fixed; left:0; right:0; top:0; z-index:5; display:flex; align-items:center; gap:var(--space-6); padding:var(--space-3) var(--space-6);
    font-size:11px; letter-spacing:.08em; text-transform:uppercase; pointer-events:none; white-space:nowrap;}
  .top b{font-weight:600;} .top span{color:color-mix(in srgb,var(--color-text) 60%,transparent); font-variant-numeric:tabular-nums;}
  .top .live{display:inline-flex; align-items:center; gap:6px;} .top .live::before{content:""; width:7px; height:7px; background:var(--color-accent); animation:pulse 2.4s infinite;}
  @keyframes pulse{0%,100%{opacity:1} 50%{opacity:.25}}
  .top a{pointer-events:auto; margin-left:auto; color:var(--color-text); text-decoration:none; border-bottom:2px solid var(--color-text); padding-bottom:1px;}
  .top a:hover{color:var(--accent-deep); border-color:var(--accent-deep);}
  /* ---- legend (HTML, bottom left) ---- */
  .legend{position:fixed; left:var(--space-6); bottom:var(--space-6); z-index:5; display:flex; gap:2px; pointer-events:none; transition:opacity .6s;}
  /* One compact row, about 30px tall. The tall three-line cells it replaced stood
     404 by 98 and sat on top of South America at the lowest zoom the map allows, and
     the map cannot zoom out past 1.0 to escape them. The flag keys are now always
     present, in every colour mode, because they are what the map is about. */
  .legend{gap:var(--space-3); align-items:center; flex-wrap:wrap; max-width:min(680px,72vw);
    background:var(--color-bg); 
    border-top:2px solid var(--color-text); padding:5px var(--space-3) 6px;}
  .legend .keys{display:flex; gap:var(--space-3); align-items:center;}
  .legend .cell{display:flex; align-items:center; gap:5px; font-size:11px; line-height:1;
    color:color-mix(in srgb,var(--color-text) 78%,transparent);}
  .legend .sw{width:15px; height:15px; display:flex; align-items:center; justify-content:center;
    font-weight:600; font-size:10px; box-sizing:border-box; flex:none;}
  .legend .pct{font-weight:600; font-variant-numeric:tabular-nums; color:var(--color-text);}
  .legend .lb{display:none;}
  .legend .ramp{display:flex; align-items:center; gap:6px;}
  .legend .ramp .bar{display:flex;} .legend .ramp .bar i{display:block; width:22px; height:11px;}
  .legend .ramp .ends{font-size:10px; font-variant-numeric:tabular-nums;
    color:color-mix(in srgb,var(--color-text) 65%,transparent);}
  .legend .sep{width:1px; height:16px; background:var(--color-divider); flex:none;}
  @media (max-width:900px){ .legend .ramp{display:none;} }
  /* ---- story column ---- */
  .story{position:relative; z-index:2; padding:0 3vw; pointer-events:none;}
  .chapter{min-height:100vh; display:flex; align-items:center; padding:12vh 0;}
  .card{pointer-events:auto; display:block; margin-left:auto; width:min(380px,100%); box-sizing:border-box; background:var(--color-bg); 
    border-top:2px solid var(--color-text); padding:var(--space-4) var(--space-6) var(--space-6); border:1px solid __HAIRLINE__; border-top:2px solid var(--color-text);
    opacity:0; transform:translateY(24px); transition:opacity .8s, transform .8s cubic-bezier(.2,.7,.1,1);}
  .chapter.on .card{opacity:1; transform:none;}
  .card .kk{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent-deep); font-weight:600; margin-bottom:var(--space-3); display:flex; justify-content:space-between; gap:var(--space-4); white-space:nowrap;}
  .card .kk span{color:color-mix(in srgb,var(--color-text) 50%,transparent); font-weight:400;}
  .card h2{font-family:var(--font-heading); font-weight:600; font-size:clamp(24px,2.1vw,32px); letter-spacing:-.03em; line-height:1.02; margin:0 0 var(--space-3); text-wrap:balance;}
  .card p{margin:0; font-size:15px; line-height:1.5; text-wrap:pretty;} .card p+p{margin-top:var(--space-3);}
  .card .num{font-family:var(--font-heading); font-weight:600; font-size:clamp(48px,5vw,76px); letter-spacing:-.05em; line-height:.95; font-variant-numeric:tabular-nums; margin:var(--space-2) 0;}
  .card .num small{font-size:.32em; letter-spacing:-.01em; font-weight:600; margin-left:.25em;}
  .hero .card{margin-left:0; width:min(900px,100%); background:transparent; box-shadow:none; padding:0; border:0;}
  .hero h1{font-family:var(--font-heading); font-weight:600; font-size:clamp(40px,6vw,110px); letter-spacing:-.05em; line-height:.92; margin:var(--space-4) 0 var(--space-6); text-wrap:balance;}
  .hero .num{font-size:clamp(56px,7.5vw,130px);}
  .hero .lead{font-size:clamp(16px,1.3vw,20px); max-width:38em;}
  .hero .scroll{margin-top:var(--space-8); font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:color-mix(in srgb,var(--color-text) 60%,transparent); display:flex; gap:10px; align-items:center;}
  .hero .scroll::before{content:""; width:32px; height:2px; background:var(--color-text);}
  /* ---- explore chapter controls ---- */
  .grp{display:flex; flex-direction:column; gap:var(--space-1); margin-top:var(--space-4);}
  .grp>span{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:color-mix(in srgb,var(--color-text) 60%,transparent);}
  .seg{display:flex; flex-wrap:wrap; border:1px solid var(--color-divider);}
  .seg button{font-size:13px; line-height:1.2; padding:7px var(--space-3); cursor:pointer; border:0; border-left:1px solid var(--color-divider); background:transparent;
    display:inline-flex; align-items:baseline; gap:var(--space-2); text-align:left; white-space:nowrap;}
  .seg button:first-child{border-left:0;} .seg button .k{font-size:10px; opacity:.55; font-variant-numeric:tabular-nums;}
  .seg button:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);}
  .seg button[aria-pressed="true"]{background:var(--color-text); color:var(--color-bg);}
  .btn{font-family:var(--font-heading); font-weight:600; font-size:13px; line-height:1.2; cursor:pointer; padding:var(--space-2) calc(var(--space-3)*1.2); border:1px solid var(--color-divider);
    background:transparent; display:inline-flex; align-items:center; gap:var(--space-2); text-align:left; white-space:nowrap; margin-top:var(--space-4);}
  .btn:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);} .btn:disabled{opacity:.45;} .btn svg{width:14px; height:14px; flex:none;}
  .chapter.explore{align-items:flex-end; padding-bottom:0;}
  .chapter.explore .card{margin:0 0 0 auto; width:100%; display:flex; flex-direction:row; flex-wrap:wrap; align-items:flex-end; gap:var(--space-2) var(--space-8); padding:var(--space-3) var(--space-6) var(--space-4);
    background:var(--color-bg); box-shadow:none; border-top:2px solid var(--color-text);}
  .chapter.explore .card .kk{width:100%; margin-bottom:0;}
  .chapter.explore .grp{margin-top:0;}
  .chapter.explore .btn{margin-top:0;}
  .chapter.explore .hint{flex:1 1 100%; margin-top:0; min-width:0;}
  .again{font-family:var(--font-heading); font-weight:600; font-size:13px; cursor:pointer; padding:var(--space-2) calc(var(--space-3)*1.2); border:1px solid var(--color-text); background:var(--color-text); color:var(--color-bg);
    display:inline-flex; align-items:center; gap:var(--space-2); white-space:nowrap; margin-left:auto;}
  .again:hover{background:var(--accent-deep); border-color:var(--accent-deep);} .again svg{width:14px; height:14px;}
  /* The write-up is the companion piece, so it sits beside "Back to the start" but
     reads as secondary: outlined rather than filled. margin-left:auto belongs to
     whichever of the two comes first, so it is cleared here. */
  .readmore{background:none; color:var(--color-text); text-decoration:none; margin-left:0;}
  .readmore:hover{background:var(--color-text); color:var(--color-bg);}
  body.atexplore .legend, body.atexplore .zoomui{bottom:calc(var(--space-6) + var(--explore-h,0px)); z-index:3;}
  .hint{font-size:12px; color:color-mix(in srgb,var(--color-text) 60%,transparent); margin-top:var(--space-3); min-height:1.5em; font-variant-numeric:tabular-nums;}
  .hidden{display:none !important;}
  /* ---- zoom ui + tooltip ---- */
  .zoomui{position:fixed; right:var(--space-6); bottom:var(--space-6); z-index:5; display:flex; border:1px solid var(--color-divider); background:var(--color-bg); opacity:0; pointer-events:none; transition:opacity .5s;}
  body.atexplore .zoomui{opacity:1; pointer-events:auto;}
  .zoomui button{font-size:15px; line-height:1; width:32px; height:32px; padding:0; border:0; border-left:1px solid var(--color-divider); background:transparent; cursor:pointer;}
  .zoomui button:first-child{border-left:0;} .zoomui button:hover{background:color-mix(in srgb,var(--color-text) 7%,transparent);}
  .zoomui #zreset{width:auto; font-size:12px; padding:0 var(--space-3);}
  .zlev{font-size:12px; line-height:32px; min-width:3.4em; text-align:center; border-left:1px solid var(--color-divider); font-variant-numeric:tabular-nums;}
  #tip{position:fixed; z-index:6; pointer-events:none; display:none; background:var(--color-bg); border:1px solid var(--color-text); font-size:13px; line-height:1.45; padding:var(--space-2) var(--space-3); width:max-content; max-width:min(90vw,480px); box-shadow:var(--shadow-md);}
  #tip b{display:block; font-family:var(--font-heading); font-weight:600; font-size:14px; margin-bottom:2px;}
  #tip .f{display:inline-block; width:.75em; height:.75em; margin-right:.4em; vertical-align:-.08em; border:1px solid transparent;} #tip .f.n{border-color:var(--nodata-border);}
  #tip table{border-collapse:collapse; margin-top:6px; font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap;}
  #tip th{font-weight:400; font-size:10px; letter-spacing:.08em; text-transform:uppercase; text-align:left; padding:0 10px 2px 0; color:color-mix(in srgb,var(--color-text) 60%,transparent); border-bottom:1px solid var(--color-divider);}
  #tip td{padding:4px 10px 0 0; white-space:nowrap;} #tip td.flag,#tip th.flag{padding-right:4px; padding-left:6px;} #tip td.flag{font-weight:600;}
  #tip td.flag span{display:inline-block; min-width:1.6em; text-align:center; outline:2px solid var(--color-accent); outline-offset:1px;}
  #tip .h{display:block; margin-top:6px; white-space:normal; max-width:28em; color:color-mix(in srgb,var(--color-text) 65%,transparent);}
  /* ---- drill-down panel ---- */
  .drill{position:fixed; top:0; right:0; bottom:0; z-index:7; width:min(420px,92vw); background:var(--color-bg); border-left:2px solid var(--color-text); padding:var(--space-8) var(--space-6);
    transform:translateX(100%); transition:transform .5s cubic-bezier(.2,.7,.1,1); overflow:auto; box-sizing:border-box;}
  .drill.open{transform:none;}
  .drill .x{position:absolute; top:var(--space-4); right:var(--space-4); width:32px; height:32px; border:1px solid var(--color-divider); background:transparent; cursor:pointer; font-size:18px; line-height:1;}
  .drill .kk{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent-deep); font-weight:600;}
  .drill h3{font-family:var(--font-heading); font-weight:600; font-size:clamp(30px,3vw,44px); letter-spacing:-.04em; line-height:1; margin:var(--space-2) 0 var(--space-6);}
  .drill table{width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums;}
  .drill th{font-weight:400; font-size:10px; letter-spacing:.08em; text-transform:uppercase; text-align:left; padding:0 0 6px; border-bottom:2px solid var(--color-text); color:color-mix(in srgb,var(--color-text) 60%,transparent);}
  .drill td{padding:10px 0; border-bottom:1px solid var(--color-divider); vertical-align:middle;}
  .drill td.sp{font-weight:600;} .drill td.v{text-align:right; white-space:nowrap;} .drill th.v{text-align:right;}
  .drill td.fl,.drill th.fl{width:44px; padding-left:var(--space-6);} .drill td.fl i{display:inline-flex; width:28px; height:28px; align-items:center; justify-content:center; font-style:normal; font-weight:600; font-size:14px;}
  .drill tr.cur td{background:color-mix(in srgb,var(--color-text) 5%,transparent);}
  .drill .src{margin-top:var(--space-6); font-size:12px; color:color-mix(in srgb,var(--color-text) 60%,transparent); line-height:1.5;}
  .drill .src code{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.92em;}
  @media (max-width:1100px){ .top span.opt{display:none;} }
  @media (max-width:760px){ .legend{display:none;} .top .live{display:none;} }""" + CSS_MONO

BODY_FIGURE = r"""<div class="wrap">
  <div class="bar">
    <div class="tabs" id="tabs" role="group" aria-label="Species"></div>
    <div class="grp"><span>Colour by</span><div class="seg" id="modebtns" role="group" aria-label="Colour by"></div></div>
    <div class="grp"><span>Projection</span><div class="seg" id="projbtns" role="group" aria-label="Projection"></div></div>
    <button class="btn" id="png" type="button"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" aria-hidden="true"><path d="M12 3v12M6 10l6 6 6-6M4 21h16"/></svg>Download PNG</button>
  </div>
  <div class="hint" id="hint"></div>
  <div class="stage">
    <svg id="map" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="ttl">
      <style>
        .country{stroke:__BORDER__; stroke-width:.25; stroke-opacity:.45; vector-effect:non-scaling-stroke;}
        .country.nodata{stroke-opacity:1;}
        /* The hover outline scales with the map rather than being pinned to a fixed
           screen width. Browsers clamp any sub-pixel stroke to about one device pixel,
           so at ordinary zooms this renders as a hairline and only thickens past about
           8x, where the country is large enough to carry it. */
        .country.hover{stroke:__INK__; stroke-width:.2; stroke-opacity:1; vector-effect:none;}
        .k0{font:600 14px __FONT_SANS__; fill:__ACCENT__; letter-spacing:1.6px;}
        .t1{font:600 96px __FONT_SANS__; fill:__INK__; letter-spacing:-3.4px;}
        .t2{font:500 21px __FONT_SANS__; fill:__INK__;}
        .t3{font:17px __FONT_SANS__; fill:__MUTED__;}
        .lgL{font:600 48px __FONT_SANS__;}
        .lgp{font:600 30px __SVG_MONO__; fill:__INK__; letter-spacing:-1px;}
        .lg{font:15px __FONT_SANS__; fill:__INK__;}
        .sc{font:14px __FONT_SANS__; fill:__MUTED__;}
        .lgc{font:600 12px __SVG_MONO__; fill:__MUTED__;}
        .lgt{font:21px __FONT_SANS__; fill:__INK__;}
        .lgk{font:600 21px __SVG_MONO__; fill:__MUTED__;}
      </style>
      <defs id="defs"><clipPath id="plotclip"><rect id="clipr" x="0" y="0" width="__W__" height="10"/></clipPath></defs>
      <rect width="100%" height="100%" fill="__GROUND__"/>
      <text id="kick" class="k0" x="40" y="34"></text>
      <text id="sub" class="t2" x="40" y="84"></text>
      <text id="sub2" class="t3" x="40" y="114"></text>
      <g id="legend" transform="translate(40,152)"></g>
      <rect id="rule" x="0" y="0" width="__W__" height="2" fill="__INK__"/>
      <g id="plot" clip-path="url(#plotclip)">
        <rect id="sea" x="0" y="0" width="__W__" height="10" fill="__SEA__"/>
        <g id="zoom"><g id="countries"></g><g id="tex"></g></g>
      </g>
    </svg>
    <div class="zoomui">
      <button id="zout" type="button" aria-label="Zoom out">&minus;</button>
      <button id="zin" type="button" aria-label="Zoom in">+</button>
      <button id="zreset" type="button" aria-label="Reset the view" title="Reset the view">&#10227;</button>
      <span class="zlev" id="zlev" hidden></span>
    </div>
    <div id="tip" role="status" aria-live="polite"></div>
  </div>
  <div class="note" id="note"></div>
</div>"""

BODY_STORY = r"""<div class="stage veil">
  <svg id="map" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="World map of 2022 livestock head counts by FAOSTAT flag" preserveAspectRatio="xMidYMid meet">
    <style>
      .country{stroke:__BORDER__; stroke-width:.25; stroke-opacity:.45; vector-effect:non-scaling-stroke;}
      .country.nodata{stroke-opacity:1;}
      .country.hover{stroke:__INK__; stroke-width:.2; stroke-opacity:1; vector-effect:none;}
    </style>
    <defs id="defs"><clipPath id="plotclip"><rect id="clipr" x="0" y="0" width="__W__" height="10"/></clipPath></defs>
    <rect width="100%" height="100%" fill="__SEA__"/>
    <g id="legend" style="display:none"></g>
    <rect id="rule" x="0" y="0" width="0" height="0" fill="none"/>
    <g id="plot" clip-path="url(#plotclip)">
      <rect id="sea" x="0" y="0" width="__W__" height="10" fill="__SEA__"/>
      <g id="zoom"><g id="countries"></g><g id="tex"></g></g>
    </g>
  </svg>
  <div id="tip" role="status" aria-live="polite"></div>
</div>
<div class="top"><b>Livestock provenance</b><span class="live">FAOSTAT QCL · release 2025-12-31</span><span class="opt" id="clock"></span><a href="map-2022.html">Open as figure</a></div>
<div class="legend" id="hlegend"></div>
<!-- Glyphs only. The zoom-level readout and the word Reset were text floating over the
     ocean with nothing around them, and neither told a reader anything they could not
     see. The labels stay on the buttons for screen readers. -->
<div class="zoomui">
  <button id="zout" type="button" aria-label="Zoom out">&minus;</button><button id="zin" type="button" aria-label="Zoom in">+</button><button id="zreset" type="button" aria-label="Reset the view" title="Reset the view">&#10227;</button>
  <span class="zlev" id="zlev" hidden></span>
</div>
<aside class="drill" id="drill" aria-hidden="true">
  <button class="x" id="drillx" type="button" aria-label="Close">&times;</button>
  <div class="kk">Area · 2022 · all five species</div>
  <h3 id="dname"></h3>
  <table><thead><tr><th>Item</th><th class="v">Head</th><th class="fl">Flag</th></tr></thead><tbody id="drows"></tbody></table>
  <p class="src">Rows are the FAOSTAT QCL records for this area, flag column included. <code>A</code> official figure, <code>E</code> country estimate, <code>I</code> FAO imputed, <code>X</code> external source. A dash means no figure was filed and none imputed.</p>
</aside>

<main class="story" id="story">
  <section class="chapter hero" data-species="Chickens" data-mode="flag" data-veil="1">
    <div class="card">
      <div class="kk">2022 · five species · FAOSTAT QCL</div>
      <div class="num"><span id="ctr">0.00</span><small>billion chickens</small></div>
      <h1>Where the world's livestock numbers come from</h1>
      <p class="lead">Cattle, sheep, goats, pigs and chickens in __YEAR__, coloured by the flag FAOSTAT attaches to each country's figure: an official national count, the country's own estimate, an FAO imputation, or a figure from an external organisation.</p>
      <div class="scroll">Scroll to read the flags</div>
    </div>
  </section>
  <section class="chapter" data-species="Chickens" data-mode="flag" data-flag="A" data-veil="1">
    <div class="card"><div class="kk">Chapter 1 <span>Flag A</span></div>
      <h2>Half the world's chickens are behind an official count.</h2>
      <div class="num">51.0<small>per cent</small></div>
      <p>87 of 184 reporting areas filed an official national figure for chickens. On the map they are solid ink. Everything else is another colour.</p></div>
  </section>
  <section class="chapter" data-species="Chickens" data-mode="flag" data-flag="I" data-zoom="1270,210,2.2">
    <div class="card"><div class="kk">Chapter 2 <span>Flag I</span></div>
      <h2>Forty per cent were never counted. The FAO imputed them.</h2>
      <div class="num">40.3<small>per cent</small></div>
      <p>78 areas, flagged I. The largest single block is China, which has not filed a chicken figure the FAO could publish as official. Amber is the one colour on this map.</p></div>
  </section>
  <section class="chapter" data-species="Cattle" data-mode="flag" data-flag="A" data-zoom="560,330,1.5">
    <div class="card"><div class="kk">Chapter 3 <span>Cattle</span></div>
      <h2>Cattle are counted. Chickens are guessed.</h2>
      <div class="num">74.3<small>per cent official</small></div>
      <p>Switch species and the ink spreads. Cattle are censused animals in most of the world; birds are not. The same country can be ink for one species and amber for the next.</p></div>
  </section>
  <section class="chapter" data-species="Chickens" data-mode="both" data-zoom="880,240,2.4">
    <div class="card"><div class="kk">Chapter 4 <span>Count and flag together</span></div>
      <h2>Read the texture on top of the number.</h2>
      <p>Colour is the head count on a log scale, one class per decade. The texture laid over a country is its flag: dots for a country estimate, a diagonal for an FAO imputation, a cross for an external source, and nothing at all for an official count. Europe files official figures at every scale, so most of it is plain; much of Africa's chicken count is a diagonal on a pale field.</p></div>
  </section>
  <section class="chapter" data-species="Chickens" data-mode="flag" data-flag="none" data-pulse="1" data-zoom="900,300,1.7">
    <div class="card"><div class="kk">Chapter 5 <span>No figure</span></div>
      <h2>Ten states filed nothing, and nothing was imputed.</h2>
      <div class="num">618<small>million birds outside the map</small></div>
      <p>The pulsing areas have no 2022 chicken row at all. About 2.3 per cent of the FAO world total sits there. Including them at their nearest reported values, all official, would raise the official share to 52 per cent.</p></div>
  </section>
  <section class="chapter explore" data-explore="1">
    <div class="card" id="explorecard"><div class="kk">Explore · now read it yourself <span>scroll to zoom · drag to pan · click a country for its five rows</span></div>
      <div class="grp"><span>Species</span><div class="seg" id="tabs" role="group" aria-label="Species"></div></div>
      <div class="grp"><span>Colour by</span><div class="seg" id="modebtns" role="group" aria-label="Colour by"></div></div>
      <div class="grp hidden"><span>Projection</span><div class="seg" id="projbtns"></div></div>
      <div class="hint" id="hint"></div>
      <button class="btn" id="png" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" aria-hidden="true"><path d="M12 3v12M6 10l6 6 6-6M4 21h16"/></svg>Download PNG</button>
__READMORE__      <button class="again" id="again" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" aria-hidden="true"><path d="M12 21V9M6 14l6-6 6 6M4 3h16"/></svg>Back to the start</button>
    </div>
  </section>
</main>
<div class="hidden"><span id="kick"></span><span id="sub"></span><span id="sub2"></span><div id="note"></div></div>"""

SCRIPT_CORE = r"""const YEAR=__YEAR__, W=__W__, TOP=__TOP__, BOTTOM=__BOTTOM__, TEXMIN=__TEXMIN__, TILE=__TILE__;
const PROJS=__PROJS__, DATA=__DATA__, SUMMARY=__SUMMARY__, SPECIES=__SPECIES__;
const COLOURS=__COLOURS__, NOROW="__NOROW__", LABEL=__LABEL__, NOTE=__NOTE__;
const NOROW_STROKE="__NOROW_STROKE__", SEA="__SEA__", GROUND="__GROUND__", INK="__INK__";
const BORDER="__BORDER__", TEX_INK_DARK="__TEX_INK_DARK__", TEX_INK_LIGHT="__TEX_INK_LIGHT__";
const TEXTURE=__TEXTURE__, TEXTURE_LABEL=__TEXTURE_LABEL__, GLYPH=__GLYPH__;
const STORY=__IS_STORY__;
let species=SPECIES[0], proj=__DEFAULT_PROJ__, mode='both';
let k=1, tx=0, ty=0;
// The figure is always interactive. In the story, pointer control is granted only in the
// final chapter, and a chapter-driven zoom relaxes the pan clamp so the card can cover the
// right of the map without hiding the subject.
let explore=!STORY, focusFlag=null, storyZoom=false;
const svgNS='http://www.w3.org/2000/svg';
const $=id=>document.getElementById(id);
const el=(t,a)=>{const e=document.createElementNS(svgNS,t); for(const q in a) e.setAttribute(q,a[q]); return e;};
const clear=n=>{while(n.firstChild) n.removeChild(n.firstChild);};

function fmtHead(h){
  if(h==null) return 'no figure';
  if(h>=1e9) return (h/1e9).toFixed(2)+' billion';
  if(h>=1e6) return (h/1e6).toFixed(1)+' million';
  if(h>=1e3) return (h/1e3).toFixed(0)+' thousand';
  return Math.round(h).toLocaleString('en-AU');
}
function fmtEdge(v){
  if(v>=1e9) return (v/1e9)+' bn';
  if(v>=1e6) return (v/1e6)+' m';
  if(v>=1e3) return (v/1e3)+' k';
  return String(v);
}
const unit=sp=>sp==='Chickens'?'birds':'animals';
// Textures ride the map up to TEX_HOLD, then hold a constant size on screen. Reflow is the
// cost of holding size, so it is confined to deep zoom where you are reading one country.
const TEX_HOLD=2.6;
const texScale=z=>Math.min(1,TEX_HOLD/z);
const rowFor=m=>(DATA[m]&&DATA[m][species])||['none',null,null];
const lum=h=>0.2126*parseInt(h.slice(1,3),16)+0.7152*parseInt(h.slice(3,5),16)+0.0722*parseInt(h.slice(5,7),16);

function classOf(h){
  const b=SUMMARY[species].bins;
  if(h==null||h<=0) return -1;
  for(let q=b.edges.length-2;q>=0;q--) if(h>=b.edges[q]) return q;
  return -1;
}
function styleFor(m){
  const row=rowFor(m), f=row[0], h=row[1];
  if(mode==='flag'){
    return f==='none' ? {fill:NOROW, stroke:NOROW_STROKE} : {fill:COLOURS[f], stroke:BORDER};
  }
  const q=classOf(h);
  if(q<0) return {fill:NOROW, stroke:NOROW_STROKE};
  return {fill:SUMMARY[species].bins.colours[q], stroke:BORDER};
}

// Texture defs are rebuilt per species because the ink colour depends on how dark the
// class underneath is: dark ink on pale fills, light ink on dark ones. The marks are the
// chart's: a dot, a 45 degree bar and a cross rule.
function buildPatterns(){
  const d=$('defs');
  [...d.querySelectorAll('pattern')].forEach(p=>p.remove());
  if(mode!=='both') return;
  const b=SUMMARY[species].bins;
  for(let q=0;q<b.colours.length;q++){
    const pale = lum(b.colours[q])>140;
    const ink = pale ? TEX_INK_DARK : TEX_INK_LIGHT;
    for(const t of ['dots','diag','cross']){
      // The chart's opacities. Dark ink on a pale ground needs a little more to hold.
      const op = ({dots:0.55, diag:0.5, cross:0.45}[t]) + (pale ? 0.15 : 0);
      // Two copies of each: 'pat-' rides the zoom transform and is counter-scaled in
      // applyZoom; 'patlg-' is for the legend, which never zooms, so it stays at 1.
      for(const variant of ['pat-','patlg-']){
        const T=TILE;
        // The same three marks as the stacked bar chart in the write-up, at the same
        // proportions of the tile: dot r 0.19T, 45 degree bar 0.31T wide, cross rule
        // 0.19T. The chart lays them over the flag colour; here they go over the ramp
        // colour, so the ink still flips with the ground's luminance.
        const rot = t==='diag' ? 'rotate(45) ' : '';
        const p=el('pattern',{id:variant+t+'-'+q, width:T, height:T,
          patternUnits:'userSpaceOnUse',
          patternTransform:rot+'scale('+(variant==='pat-'?texScale(k):1)+')'});
        p.dataset.rot=rot;
        if(t==='dots'){
          p.appendChild(el('circle',{cx:T/2, cy:T/2, r:T*0.19, fill:ink, 'fill-opacity':op}));
        } else if(t==='diag'){
          p.appendChild(el('rect',{x:0, y:0, width:T*0.314, height:T, fill:ink, 'fill-opacity':op}));
        } else {
          p.appendChild(el('path',{d:'M0 '+(T/2)+'H'+T+'M'+(T/2)+' 0V'+T,
            stroke:ink, 'stroke-opacity':op, 'stroke-width':T*0.19, fill:'none'}));
        }
        d.appendChild(p);
      }
    }
  }
}

const G=$('countries'), TX=$('tex');
let nodes={}, areas={}, cent={};

function buildGeometry(){
  clear(G); clear(TX); nodes={}; areas={}; cent={};
  const d=$('defs');
  [...d.querySelectorAll('path.geo')].forEach(function(n){n.remove();});
  const P=PROJS[proj];
  for(const p of P.paths){
    d.appendChild(el('path',{d:p.d,id:'d'+p.i,class:'geo'}));
    const u=el('use',{href:'#d'+p.i,class:'country',id:'g'+p.i});
    u.__m=p.m; u.__n=p.n;
    G.appendChild(u); nodes[p.i]=u;
  }
  // True projected land area per country, computed at build time, used to decide whether
  // a texture is legible at the current zoom. Screen area is this times k squared. Not the
  // bounding box: a country crossing the antimeridian has one spanning the whole map.
  for(const p of P.paths){ areas[p.i]=p.a; const bb=nodes[p.i].getBBox(); cent[p.i]=[bb.x+bb.width/2, bb.y+bb.height/2]; }
  const total=TOP+P.H+BOTTOM;
  $('map').setAttribute('viewBox','0 0 '+W+' '+total);
  $('plot').setAttribute('transform','translate(0,'+TOP+')');
  $('clipr').setAttribute('height',P.H);
  $('sea').setAttribute('height',P.H);
  if(!STORY) $('rule').setAttribute('y',TOP-2);
}

function applyZoom(){
  const P=PROJS[proj];
  k=Math.max(1,Math.min(12,k));
  tx=Math.max(W-W*k-(storyZoom?W*0.5:0),Math.min(0,tx));
  ty=Math.max(P.H-P.H*k,Math.min(0,ty));
  // The story animates between chapters, so it drives a CSS transform that can transition;
  // the figure sets the attribute directly and snaps.
  if(STORY) $('zoom').style.transform='translate('+tx+'px,'+ty+'px) scale('+k+')';
  else $('zoom').setAttribute('transform','translate('+tx+','+ty+') scale('+k+')');
  $('zlev').textContent=k.toFixed(1)+'x';
  // Textures must not grow with the map or they stop reading as texture.
  [...$('defs').querySelectorAll('pattern')].forEach(function(p){
    if(p.id.indexOf('pat-')===0) p.setAttribute('patternTransform',(p.dataset.rot||'')+'scale('+texScale(k)+')');
  });
}

function paint(){
  const P=PROJS[proj], s=SUMMARY[species];
  for(const p of P.paths){
    const st=styleFor(p.m);
    nodes[p.i].setAttribute('fill', st.fill);
    nodes[p.i].setAttribute('stroke', st.stroke);
    nodes[p.i].classList.toggle('nodata', st.fill===NOROW);
  }
  buildPatterns();
  clear(TX);
  let tooSmall=0, textured=0;
  if(mode==='both'){
    for(const p of P.paths){
      const row=rowFor(p.m), f=row[0], h=row[1];
      const t=TEXTURE[f];
      if(!t||t==='solid') continue;
      const q=classOf(h); if(q<0) continue;
      textured++;
      if(areas[p.i]*k*k<TEXMIN){ tooSmall++; continue; }
      TX.appendChild(el('use',{href:'#d'+p.i,fill:'url(#pat-'+t+'-'+q+')',stroke:'none'}));
    }
  }

  $('kick').textContent=('FAOSTAT observation status flags · '+species+' · '+YEAR).toUpperCase();
  $('sub').textContent=species+', '+YEAR+': '+s.head_billions.toFixed(2)+' billion '+unit(species)+', '+
    s.share_of_set_pct+' per cent of the five species, across '+s.reporting_areas+' reporting areas.';
  if(mode==='flag'){
    $('sub2').textContent=s.by.A.pct.toFixed(1)+' per cent sit behind an official national count ('+s.pct_official_by_area.toFixed(1)+' per cent of the reporting areas).';
    $('hint').textContent='Hover a country. Keys 1 to 5 switch species. Scroll to zoom, drag to pan.';
  } else {
    $('sub2').textContent='Head counts run from '+fmtHead(s.bins.min)+' to '+fmtHead(s.bins.max)+
      '. Colour is a log scale, one class per decade, for '+species.toLowerCase()+' only.';
    $('hint').textContent = mode==='both'
      ? 'Colour is the head count, texture is the flag. '+(tooSmall
          ? tooSmall+' of '+textured+' textured countries are too small to show their texture at '+k.toFixed(1)+'x. Zoom in to read them.'
          : 'All '+textured+' textured countries are large enough to read at '+k.toFixed(1)+'x.')
      : 'Hover a country. Keys 1 to 5 switch species. The scale is rebuilt for each species, so colours are not comparable between them.';
  }

  const L=$('legend'); clear(L); let x=0;
  const txt=function(x,y,cls,str,fill){const t=el('text',{x:x,y:y,class:cls}); if(fill) t.setAttribute('fill',fill); t.textContent=str; L.appendChild(t); return t.getComputedTextLength();};
  const CODE={A:'A',E:'E',I:'I',X:'X',none:'–'};
  const inkOn=function(c){return lum(c)>140?INK:'#ffffff';};
  const LW=W-80, GAP=8, BH=72;
  if(mode==='flag'){
    const items=[['A',s.by.A.pct],['E',s.by.E.pct],['I',s.by.I.pct],['X',s.by.X.pct],['none',null]];
    const cw=(LW-GAP*(items.length-1))/items.length;
    items.forEach(function(it,i){
      const f=it[0], pct=it[1], cx=i*(cw+GAP), none=f==='none';
      L.appendChild(el('rect',{x:cx,y:0,width:cw,height:BH,fill:none?NOROW:COLOURS[f],stroke:none?NOROW_STROKE:'none'}));
      txt(cx+14,BH-18,'lgL',CODE[f],none?INK:inkOn(COLOURS[f]));
      if(pct!=null) txt(cx,BH+40,'lgp',pct.toFixed(1)+'%');
      txt(cx,BH+(pct!=null?66:40),'lg',LABEL[f]);
    });
  } else {
    const b=s.bins, n=b.colours.length;
    const cw=(LW-GAP-330)/n;
    txt(0,-12,'sc',unit(species)[0].toUpperCase()+unit(species).slice(1)+' per country, log scale, '+species.toLowerCase()+' only');
    for(let q=0;q<n;q++){
      L.appendChild(el('rect',{x:q*cw,y:0,width:cw,height:BH,fill:b.colours[q],stroke:'none'}));
      txt(q*cw,BH+24,'sc',fmtEdge(b.edges[q]));
    }
    txt(n*cw,BH+24,'sc',fmtEdge(b.edges[n]));
    const nx=n*cw+GAP+50;
    L.appendChild(el('rect',{x:nx,y:0,width:LW-nx,height:BH,fill:NOROW,stroke:NOROW_STROKE}));
    txt(nx+14,BH-18,'lgL',CODE.none,INK);
    txt(nx,BH+24,'sc',LABEL['none']);
    if(mode==='both'){
      // In this mode the texture carries the whole flag reading, so its key is a row of
      // real swatches at reading size rather than a footnote. The ground is neutral and
      // the mark is the dark-ink variant, which is what a pale country shows.
      x=0; const ty=BH+56, sw=72, sh=34;
      x+=txt(0,ty+23,'lgt','Texture is the flag')+26;
      for(const f of ['A','E','I','X']){
        const t=TEXTURE[f];
        L.appendChild(el('rect',{x:x,y:ty,width:sw,height:sh,fill:'__WELL__',stroke:NOROW_STROKE}));
        if(t!=='solid') L.appendChild(el('rect',{x:x,y:ty,width:sw,height:sh,fill:'url(#patlg-'+t+'-0)',stroke:'none'}));
        x+=sw+12;
        x+=txt(x,ty+23,'lgt',LABEL[f])+10;
        x+=txt(x,ty+23,'lgk',CODE[f])+30;
      }
    }
  }

  const Nn=$('note'); clear(Nn);
  for(const para of NOTE){ const p=document.createElement('p'); p.textContent=para; Nn.appendChild(p); }
  document.querySelectorAll('#tabs button').forEach(function(b){b.setAttribute('aria-pressed', b.dataset.sp===species?'true':'false');});
  document.querySelectorAll('#projbtns button').forEach(function(b){b.setAttribute('aria-pressed', b.dataset.p===proj?'true':'false');});
  document.querySelectorAll('#modebtns button').forEach(function(b){b.setAttribute('aria-pressed', b.dataset.m===mode?'true':'false');});
  applyZoom();
}

const T=$('tabs');
SPECIES.forEach(function(sp,i){
  const b=document.createElement('button'); b.type='button'; b.dataset.sp=sp;
  const kk=document.createElement('span'); kk.className='k'; kk.textContent=String(i+1);
  b.appendChild(kk); b.appendChild(document.createTextNode(sp));
  b.addEventListener('click',function(){species=sp; paint();}); T.appendChild(b);
});
const MB=$('modebtns');
[['flag','Flag'],['count','Count'],['both','Count + flag']].forEach(function(pair){
  const b=document.createElement('button'); b.type='button'; b.textContent=pair[1]; b.dataset.m=pair[0];
  b.addEventListener('click',function(){mode=pair[0]; paint();}); MB.appendChild(b);
});
const PB=$('projbtns');
Object.keys(PROJS).forEach(function(key){
  const b=document.createElement('button'); b.type='button'; b.textContent=PROJS[key].label; b.dataset.p=key;
  b.addEventListener('click',function(){proj=key; k=1; tx=0; ty=0; buildGeometry(); paint();}); PB.appendChild(b);
});
document.addEventListener('keydown',function(e){const q=parseInt(e.key,10); if(q>=1&&q<=SPECIES.length){species=SPECIES[q-1]; paint();}});

// --- zoom and pan ---
const stage=document.querySelector('.stage'), tip=$('tip');
function svgPoint(ev){
  const r=$('map').getBoundingClientRect(), P=PROJS[proj], total=TOP+P.H;
  // The figure fills its width. The story letterboxes the whole world into the viewport,
  // so the pointer must be mapped through the same fit the SVG is using.
  if(!STORY){ const scale=r.width/W; return {x:(ev.clientX-r.left)/scale, y:(ev.clientY-r.top)/scale-TOP, H:P.H}; }
  const scale=Math.min(r.width/W, r.height/total),
        ox=r.left+(r.width-W*scale)/2, oy=r.top+(r.height-total*scale)/2;
  return {x:(ev.clientX-ox)/scale, y:(ev.clientY-oy)/scale-TOP, H:P.H};
}
function zoomAt(px,py,factor){
  const cx=(px-tx)/k, cy=(py-ty)/k;
  k=Math.max(1,Math.min(12,k*factor));
  tx=px-cx*k; ty=py-cy*k;
  applyZoom(); paint();
}
$('map').addEventListener('wheel',function(ev){
  if(!explore) return;
  const p=svgPoint(ev);
  if(p.y<0||p.y>p.H) return;      // only over the map itself, not the title or the note
  ev.preventDefault();
  zoomAt(p.x,p.y,ev.deltaY<0?1.18:1/1.18);
},{passive:false});
$('zin').addEventListener('click',function(){const P=PROJS[proj]; zoomAt(W/2,P.H/2,1.4);});
$('zout').addEventListener('click',function(){const P=PROJS[proj]; zoomAt(W/2,P.H/2,1/1.4);});
$('zreset').addEventListener('click',function(){k=1;tx=0;ty=0;applyZoom();paint();});

let dragging=false,lastX=0,lastY=0,moved=false;
$('map').addEventListener('mousedown',function(ev){
  if(!explore) return;
  const p=svgPoint(ev); if(p.y<0||p.y>p.H) return;
  dragging=true; moved=false; lastX=ev.clientX; lastY=ev.clientY;
  $('zoom').classList.add('dragging');
});
window.addEventListener('mouseup',function(){dragging=false; $('zoom').classList.remove('dragging');});
window.addEventListener('mousemove',function(ev){
  if(!dragging) return;
  const r=$('map').getBoundingClientRect(), scale=r.width/W;
  tx+=(ev.clientX-lastX)/scale; ty+=(ev.clientY-lastY)/scale;
  lastX=ev.clientX; lastY=ev.clientY; moved=true; hide(); applyZoom();
});

// --- tooltip: the source row, with the flag column the piece is about ---
let hovered=null;
function show(path,ev){
  const row=rowFor(path.__m), f=row[0], h=row[1], area=row[2];
  const esc=function(x){return String(x).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});};
  tip.innerHTML='<b>'+esc(area||path.__n)+'</b><span class="f'+(f==='none'?' n':'')+'" style="background:'+(COLOURS[f]||NOROW)+'"></span>'+LABEL[f]+
    '<table><tr><th>Area</th><th>Item</th><th>Year</th><th>Value</th><th class="flag">Flag</th></tr>'+
    '<tr><td>'+esc(area||path.__n)+'</td><td>'+esc(species)+'</td><td>'+YEAR+'</td><td>'+(h!=null?Math.round(h).toLocaleString('en-AU'):'—')+'</td>'+
    '<td class="flag"><span>'+(COLOURS[f]?f:'—')+'</span></td></tr></table>'+
    '<span class="h">'+(h!=null?fmtHead(h)+' '+unit(species)+'. ':'')+'The flag is the column downstream users drop.</span>';
  tip.style.display='block';
  const r=stage.getBoundingClientRect();
  let x=ev.clientX-r.left+14, y=ev.clientY-r.top+14;
  if(x+tip.offsetWidth>r.width-8) x=ev.clientX-r.left-tip.offsetWidth-14;
  if(y+tip.offsetHeight>r.height-8) y=ev.clientY-r.top-tip.offsetHeight-14;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
G.addEventListener('mousemove',function(ev){
  if(dragging){hide(); return;}
  const p=ev.target.closest('.country'); if(!p){hide(); return;}
  if(hovered&&hovered!==p) hovered.classList.remove('hover');
  hovered=p; p.classList.add('hover'); show(p,ev);
});
function hide(){ if(hovered){hovered.classList.remove('hover'); hovered=null;} tip.style.display='none'; }
G.addEventListener('mouseleave',hide);

// Schibsted Grotesk and JetBrains Mono are web fonts, so the PNG renderer only sees them if
// the faces are embedded in the serialised SVG. Fetched once, cached; falls back to system-ui.
let fontCSS=null;
async function embeddedFont(){
  if(fontCSS!==null) return fontCSS;
  try{
    const css=await (await fetch('__FONT_HREF__')).text();
    const urls=[...css.matchAll(/url\(([^)]+)\)/g)].map(function(m){return m[1];});
    let out=css;
    for(const u of urls){
      const blob=await (await fetch(u)).blob();
      const data=await new Promise(function(r){const fr=new FileReader(); fr.onload=function(){r(fr.result);}; fr.readAsDataURL(blob);});
      out=out.split(u).join(data);
    }
    fontCSS=out;
  }catch(e){ fontCSS=''; }
  return fontCSS;
}
async function renderCanvas(scale){
  const fcss=await embeddedFont();
  return new Promise(function(resolve,reject){
    const svg=$('map'), P=PROJS[proj], total=TOP+P.H+BOTTOM;
    const clone=svg.cloneNode(true);
    if(fcss){ const fs=document.createElementNS(svgNS,'style'); fs.textContent=fcss; clone.insertBefore(fs,clone.firstChild); }
    clone.querySelectorAll('.hover').forEach(function(e){e.classList.remove('hover');});
    // In the export the stroke should scale with the render size; non-scaling-stroke would
    // pin it to a fraction of a device pixel in a 4800 px image and alias away.
    const ov=document.createElementNS(svgNS,'style');
    ov.textContent='.country{vector-effect:none;}';
    clone.insertBefore(ov,clone.firstChild);
    clone.setAttribute('width',W*scale); clone.setAttribute('height',total*scale);
    const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],
      {type:'image/svg+xml;charset=utf-8'}));
    const img=new Image();
    img.onload=function(){const c=document.createElement('canvas'); c.width=W*scale; c.height=Math.round(total*scale);
      const ctx=c.getContext('2d'); ctx.fillStyle=GROUND; ctx.fillRect(0,0,c.width,c.height);
      ctx.drawImage(img,0,0); URL.revokeObjectURL(url); resolve(c);};
    img.onerror=function(e){URL.revokeObjectURL(url); reject(e);};
    img.src=url;
  });
}
window.renderCanvas=renderCanvas;
$('png').addEventListener('click',async function(){
  const b=$('png'); b.disabled=true; b.textContent='Rendering';
  try{
    const c=await renderCanvas(3);
    c.toBlob(function(blob){const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
      a.download='map-'+YEAR+'-'+species.toLowerCase()+'-'+mode+'-'+proj+'.png'; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){URL.revokeObjectURL(a.href);},2000);},'image/png');
  } finally { b.disabled=false; b.textContent='Download PNG'; }
});
"""

# The story engine: chapter state, the scroll observer, the HTML legend, the counter
# and the per-country drill-down. Appended after SCRIPT_CORE, which it wraps, not forks.

SCRIPT_STORY = r"""
// ---------------- story engine ----------------
// explore, focusFlag and storyZoom are declared in SCRIPT_CORE, which branches on them.
function setHighlight(){
  for(const i in nodes){
    const f=rowFor(nodes[i].__m)[0];
    const dim=focusFlag!=null && f!==focusFlag;
    nodes[i].classList.toggle('dim',dim);
  }
  [...TX.children].forEach(function(u){ const i=u.getAttribute('href').slice(2); const f=rowFor(nodes[i].__m)[0]; u.classList.toggle('dim', focusFlag!=null && f!==focusFlag); });
}
// The story card covers the right half, so the point of interest is placed about 30% in from the left.
function zoomTo(cx,cy,kk){ storyZoom=true; k=kk; tx=W*0.28-cx*kk; ty=PROJS[proj].H/2-cy*kk; applyZoom(); paint(); }
function htmlLegend(){
  const s=SUMMARY[species], L=$('hlegend'); L.innerHTML='';
  const inkOn=function(c){return lum(c)>140?'__FLAG_A__':'__BORDER__';};
  // The flag keys are drawn in EVERY mode. They were previously hidden in count mode
  // and reduced to a one-line footnote in count-and-flag mode, which left the marks on
  // the map with nothing on screen saying what they meant.
  // The map stamps a texture on every flagged country in count-and-flag mode, so the
  // key carries the same mark. Same geometry and opacities as the stacked bar chart in
  // the write-up, laid over the flag colour exactly as the chart lays it.
  const texCss=function(f){
    if(mode!=='both') return '';
    const t=TEXTURE[f], a=function(o){return 'rgba(255,255,255,'+o+')';};
    if(t==='dots')  return 'radial-gradient(circle at 50% 50%, '+a(.55)+' 0 1.4px, transparent 1.5px) 0 0/7px 7px, ';
    if(t==='diag')  return 'repeating-linear-gradient(45deg, '+a(.5)+' 0 2.2px, transparent 2.2px 7px), ';
    if(t==='cross') return 'repeating-linear-gradient(0deg, '+a(.45)+' 0 1.3px, transparent 1.3px 7px), repeating-linear-gradient(90deg, '+a(.45)+' 0 1.3px, transparent 1.3px 7px), ';
    return '';
  };
  const keys=document.createElement('div'); keys.className='keys';
  [['A',s.by.A.pct],['E',s.by.E.pct],['I',s.by.I.pct],['X',s.by.X.pct],['none',null]].forEach(function(it){
    const f=it[0], none=f==='none', c=none?NOROW:COLOURS[f];
    const d=document.createElement('div'); d.className='cell';
    d.title=LABEL[f]+(it[1]!=null?', '+it[1].toFixed(1)+' per cent of '+species.toLowerCase():'');
    d.innerHTML='<div class="sw" style="background:'+(none?'':texCss(f))+c+';color:'+(none?'__FLAG_A__':inkOn(c))+(none?';outline:1px solid '+NOROW_STROKE+';outline-offset:-1px':'')+'">'+(none?'–':f)+'</div>'
      +(it[1]!=null?'<span class="pct">'+it[1].toFixed(1)+'%</span>':'<span>none</span>');
    if(focusFlag!=null && f!==focusFlag) d.style.opacity='.35';
    keys.appendChild(d);
  });
  L.appendChild(keys);
  if(mode!=='flag'){
    const b=s.bins, d=document.createElement('div'); d.className='ramp';
    const e=b.edges.slice(0,b.colours.length);
    L.appendChild(Object.assign(document.createElement('div'),{className:'sep'}));
    d.innerHTML='<span class="ends">'+fmtEdge(e[0])+'</span>'
      +'<div class="bar">'+b.colours.map(function(c){return '<i style="background:'+c+'"></i>';}).join('')+'</div>'
      +'<span class="ends">'+fmtEdge(b.edges[b.colours.length])+' '+species.toLowerCase()+'</span>';
    L.appendChild(d);
  }
}
const _paint=paint;
paint=function(){ _paint(); setHighlight(); htmlLegend(); };
// chapters
const chapters=[...document.querySelectorAll('.chapter')];
function enter(ch){
  chapters.forEach(function(c){c.classList.toggle('on',c===ch);});
  explore=!!ch.dataset.explore;
  // 'atexplore' means the toolbar is on screen, so the legend and zoom controls lift clear of it.
  // 'explore' means it is fully in view and the page should stop scrolling; that one belongs to
  // the second observer, so clearing it here would undo the lift the moment both fire.
  document.body.classList.toggle('atexplore', explore);
  if(!explore) document.body.classList.remove('explore');
  document.querySelector('.stage').classList.toggle('veil', !!ch.dataset.veil);
  document.querySelector('.stage').classList.toggle('pulse', !!ch.dataset.pulse);
  $('hlegend').style.opacity = ch.classList.contains('hero') ? '0' : '1';
  if(ch.dataset.species) species=ch.dataset.species;
  if(ch.dataset.mode) mode=ch.dataset.mode;
  focusFlag=ch.dataset.flag||null;
  storyZoom=false;
  if(explore){ focusFlag=null; k=1; tx=0; ty=0; applyZoom(); paint(); return; }
  if(ch.dataset.zoom){ const z=ch.dataset.zoom.split(',').map(Number); zoomTo(z[0],z[1],z[2]); }
  else { k=1; tx=0; ty=0; applyZoom(); paint(); }
}
const io=new IntersectionObserver(function(es){
  es.forEach(function(e){ if(e.isIntersecting) enter(e.target); });
},{threshold:.55});
chapters.forEach(function(c){io.observe(c);});
// explore: engage full pointer control once the last chapter is reached
const ioX=new IntersectionObserver(function(es){ es.forEach(function(e){ document.body.classList.toggle('explore', e.isIntersecting && e.intersectionRatio>.9); }); },{threshold:[.9]});
function exploreH(){ document.documentElement.style.setProperty('--explore-h', $('explorecard').offsetHeight+'px'); }
window.addEventListener('resize',exploreH); exploreH(); new ResizeObserver(exploreH).observe($('explorecard'));
$('again').addEventListener('click',function(){ $('drillx').click(); window.scrollTo({top:0,behavior:'smooth'}); });
ioX.observe(document.querySelector('.chapter.explore'));
// counter
(function(){ const t0=performance.now(), target=SUMMARY.Chickens.head_billions, el=$('ctr');
  function step(t){ const p=Math.min(1,(t-t0)/1800), e=1-Math.pow(1-p,3); el.textContent=(target*e).toFixed(2); if(p<1) requestAnimationFrame(step); }
  requestAnimationFrame(step); })();
// clock
(function(){ const c=$('clock'); function tick(){ const d=new Date(); c.textContent='Loaded '+d.toLocaleDateString('en-AU',{day:'2-digit',month:'short',year:'numeric'})+' '+d.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'}); } tick(); setInterval(tick,30000); })();
// drill-down
const drill=$('drill');
function openDrill(m,name){
  const rows=DATA[m]||{}; $('dname').textContent=name; const tb=$('drows'); tb.innerHTML='';
  SPECIES.forEach(function(sp){
    const r=rows[sp]||['none',null,name], f=r[0], h=r[1], none=f==='none', c=none?NOROW:COLOURS[f];
    const tr=document.createElement('tr'); if(sp===species) tr.className='cur';
    tr.innerHTML='<td class="sp">'+sp+'</td><td class="v">'+(h!=null?Math.round(h).toLocaleString('en-AU'):'—')+'</td>'
      +'<td class="fl"><i style="background:'+c+';color:'+(none?'__FLAG_A__':(lum(c)>140?'__FLAG_A__':'#fff'))+(none?';outline:1px solid '+NOROW_STROKE:'')+'">'+(none?'–':f)+'</i></td>';
    tb.appendChild(tr);
  });
  drill.classList.add('open'); drill.setAttribute('aria-hidden','false');
}
$('drillx').addEventListener('click',function(){drill.classList.remove('open'); drill.setAttribute('aria-hidden','true');});
G.addEventListener('click',function(ev){ if(!explore||moved) return; const p=ev.target.closest('.country'); if(p) openDrill(p.__m,p.__n); });
document.addEventListener('keydown',function(e){ if(e.key==='Escape') $('drillx').click(); });

"""

if __name__ == '__main__':
    main()
    main(out='out/map-2022-story.html', story=True)
