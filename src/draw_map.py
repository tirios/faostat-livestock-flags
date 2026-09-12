"""The map: for each core species, which countries' head count is a figure someone counted.

One year, one species, one country gives exactly one flag, so the encoding is categorical
and no averaging happens. That is deliberate: averaging over an unfixed species set is the
trap that makes a country reporting three species, all official, outscore one reporting
fourteen.

Run:  .venv/Scripts/python src/draw_map.py
Out:  out/map-2022.png, out/map-2022-coverage.csv, out/small-countries-2022.csv
"""

import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

YEAR = 2022
CORE = ['Chickens', 'Cattle', 'Sheep', 'Goats', 'Swine / pigs']
LABEL = {'Swine / pigs': 'Pigs'}

# These are the SAME four values the interactive map and the stacked bar chart use.
# Until 12 September this file carried its own scheme, chosen independently and with
# its own colour-vision reasoning: blue, pale blue, burnt orange and black. That meant
# the print figure and the interactive map gave the same four categories four different
# colours, and this PNG is the preview image the write-up embeds for the map it links
# to. The design system's rule is that a reader moving between them must not meet a
# different colour meaning the same thing, so the print figure now follows the other
# two. Separations were measured for this palette rather than asserted: every flag pair
# is at least 23.1 CIEDE2000 under normal, protanopic and deuteranopic vision.
COLOURS = {
    'A': '#1E1B2E',   # official national figure
    'E': '#6B7BF0',   # country's own estimate
    'I': '#FFB020',   # imputed by the FAO
    'X': '#17A88A',   # external organisation
}
# Ocean and page are one surface, so the coastline is the edge and the only tinted
# thing on the sheet is the land that filed nothing, which is the finding. Sea against
# no-figure measures 6.9, so the border is what does that work, not the fill.
NOROW = '#ECE7DD'
NOROW_EDGE = '#C4C9CC'
SEA = '#FFFFFF'

# Output resolution. This is NOT free to change: src/make_numbers.py reads
# out/small-countries-2022.csv, whose px2 column is computed from this number, and the
# published "renders smaller than eight pixels square" finding rests on it. Raising DPI
# changes which countries fall under the threshold, so the figure, numbers.json and every
# document quoting them have to be regenerated together.
DPI = 165
LEGEND = [('A', 'Official national figure'),
          ('E', 'Country estimate'),
          ('I', 'FAO imputed'),
          ('X', 'External organisation'),
          (None, f'No figure for this species in {YEAR}')]

# Natural Earth carries the -099 sentinel for both, so neither can be joined on its UN
# code. 578 and 158 are the M49 codes. NOTE the trap that cost a wrong map once: FAOSTAT
# carries BOTH an 'Area Code' and an 'Area Code (M49)', and Taiwan's area code 214 is the
# Dominican Republic's M49. Joining on the wrong one drew Taiwan with Dominican data.
NAME_M49 = {'Norway': '578', 'Taiwan': '158'}
SENTINEL = '-099'

EQUAL_EARTH = '+proj=eqearth +lon_0=0 +datum=WGS84 +units=m +no_defs'


def load_geo():
    g = gpd.read_file('data/geo/ne_50m_admin_0_countries.geojson')
    g = g[g['NAME'] != 'Antarctica'].copy()
    g['m49'] = g['UN_A3'].astype(str).str.zfill(3)
    for name, code in NAME_M49.items():
        n = (g['NAME'] == name).sum()
        assert n == 1, f'expected exactly one {name} geometry, found {n}'
        g.loc[g['NAME'] == name, 'm49'] = code

    # Two geometries sharing a code means one country is about to be painted with
    # another's data. Only the sentinel may repeat. This assertion fires on the old
    # Taiwan bug, which is how it earned its place.
    dup = set(g.loc[g['m49'].duplicated(keep=False), 'm49']) - {SENTINEL}
    assert not dup, f'geometries share an M49 code, one will take the other\'s data: {dup}'
    return g.to_crs(EQUAL_EARTH)


def load_flags():
    df = pd.read_csv('out/stocks.csv.gz')
    missing = set(CORE) - set(df['Item'])
    assert not missing, f'core species names match nothing in this release: {missing}'
    d = df[(df['Year'] == YEAR) & (df['Item'].isin(CORE))].copy()
    d['m49'] = d['Area Code (M49)'].astype(str).str.lstrip("'").str.zfill(3)

    # An unrecognised flag would fall through to the no-data colour and vanish silently.
    # The FAO changed this vocabulary once already, between 2014 and 2015.
    unknown = set(d['Flag'].dropna()) - set(COLOURS)
    assert not unknown, f'flag values with no colour, they would render as no-data: {unknown}'
    return df, d


def gap_countries(df, species='Chickens'):
    """Countries that report this species in other years but filed nothing for YEAR.

    They render in the no-data colour, which is why the legend cannot say the species is
    not reported there. For chickens this is ten European states carrying about 618
    million birds, all official in their nearest year.
    """
    s = df[df['Item'] == species]
    ever = set(s['Area'])
    now = set(s[s['Year'] == YEAR]['Area'])
    gaps = sorted(ever - now)
    near = []
    for a in gaps:
        h = s[(s['Area'] == a) & (s['Flag'].notna())]
        if len(h):
            row = h.iloc[(h['Year'] - YEAR).abs().argsort()].iloc[0]
            near.append({'area': a, 'nearest_year': int(row['Year']),
                         'head': row['head'], 'flag': row['Flag']})
    return pd.DataFrame(near)


def main():
    geo = load_geo()
    df, d = load_flags()

    fig, axes = plt.subplots(3, 2, figsize=(13.5, 12.9))
    axes = axes.ravel()
    cover = []

    for i, sp in enumerate(CORE):
        ax = axes[i]
        s = d[d['Item'] == sp][['m49', 'Flag', 'head']]

        unmatched = sorted(set(s['m49']) - set(geo['m49']))
        assert not unmatched, f'{sp}: FAO areas with no geometry: {unmatched}'

        m = geo.merge(s, on='m49', how='left')
        assert len(m) == len(geo), f'{sp}: merge changed row count, join is not one-to-one'

        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor=SEA, edgecolor='none', zorder=-1))
        # The sea is now paper, so a white coastline is invisible against it and the
        # no-figure fill sits only 6.9 CIEDE2000 from the sea. Land that filed nothing
        # therefore takes the mid rule as its edge and everything else keeps the white
        # hairline that separates neighbours. Without this, a no-data country on a white
        # ocean has no edge at all and simply disappears, which is the same defect this
        # figure already had once when the sea was white.
        edges = m['Flag'].notna().map({True: 'white', False: NOROW_EDGE})
        widths = m['Flag'].notna().map({True: 0.12, False: 0.3})
        m.plot(ax=ax, color=m['Flag'].map(COLOURS).fillna(NOROW),
               edgecolor=edges.tolist(), linewidth=widths.tolist())

        tot = s['head'].sum()
        off = s[s['Flag'] == 'A']['head'].sum() / tot * 100
        areas = s['m49'].nunique()
        off_areas = (s['Flag'] == 'A').mean() * 100
        cover.append({'species': LABEL.get(sp, sp), 'fao_rows_in': len(s),
                      'geo_matched': int(m['Flag'].notna().sum()),
                      'fao_unmatched': len(unmatched),
                      'reporting_areas': areas, 'head_millions': round(tot / 1e6, 1),
                      'pct_animals_official': round(off, 1),
                      'pct_areas_official': round(off_areas, 1)})

        name = LABEL.get(sp, sp)
        unit = 'birds' if sp == 'Chickens' else 'animals'
        ax.set_title(f'{name}   {tot/1e9:.2f} billion {unit}', loc='left', x=0,
                     fontsize=12.5, color='#141618', pad=5)
        ax.text(0, 1.004, f'{off:.0f} per cent sit behind an official national count '
                          f'({off_areas:.0f} per cent of the {areas} reporting areas)',
                transform=ax.transAxes, fontsize=8.8, color='#5A6167', va='bottom')
        ax.set_axis_off()

    # Sixth cell: where the imputation actually is. On the map China is one orange
    # polygon among many, which hides that it is most of the story.
    ax = axes[5]
    ax.set_axis_off()

    allc = d.groupby('Flag')['head'].sum()
    tot = allc.sum()
    pct = {k: allc.get(k, 0) / tot * 100 for k in 'AEIX'}
    ch_share = d[d['Item'] == 'Chickens']['head'].sum() / tot * 100
    nc = d[~((d['Item'] == 'Chickens') & (d['Area'] == 'China, mainland'))]
    nc_pct = {k: nc[nc['Flag'] == k]['head'].sum() / nc['head'].sum() * 100 for k in 'AI'}

    ax.text(0, 0.97, f'Across these five species in {YEAR}, weighted by head',
            transform=ax.transAxes, fontsize=11.5, color='#141618', va='top')
    lines = [f"{pct['A']:.0f} per cent  official national figures",
             f"{pct['E']:.0f} per cent  country estimates",
             f"{pct['I']:.0f} per cent  FAO imputations",
             f"{pct['X']:.1f} per cent  external sources"]
    ax.text(0, 0.895, '\n'.join(lines), transform=ax.transAxes, fontsize=10.5,
            color='#3A4045', va='top', linespacing=1.6, family='DejaVu Sans')

    top = (d[d['Flag'] == 'I'].nlargest(3, 'head')
           [['Area', 'Item', 'head']].reset_index(drop=True))
    imp = d[d['Flag'] == 'I']['head'].sum()
    rows = '\n'.join(f"{r['Area']}, {LABEL.get(r['Item'], r['Item']).lower()}"
                     f"   {r['head']/1e9:.2f} bn   {r['head']/imp*100:.0f} per cent"
                     for _, r in top.iterrows())
    ax.text(0, 0.545, 'Three rows are most of the imputation', transform=ax.transAxes,
            fontsize=11.5, color='#141618', va='top')
    ax.text(0, 0.462, rows, transform=ax.transAxes, fontsize=9.8, color='#3A4045',
            va='top', linespacing=1.7)
    ax.text(0, 0.215,
            f"Chickens are {ch_share:.0f} per cent of these animals. Excluding China's\n"
            f"mainland chicken count alone, the official share rises to {nc_pct['A']:.0f} per\n"
            f"cent and the imputed share falls to {nc_pct['I']:.0f} per cent.",
            transform=ax.transAxes, fontsize=9.4, color='#5A6167', va='top', linespacing=1.6)

    handles = [Patch(facecolor=COLOURS[k] if k else NOROW, edgecolor='white', label=lab)
               for k, lab in LEGEND]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(0.043, 0.933),
               ncol=5, frameon=False, fontsize=10, handlelength=1.5, columnspacing=1.6)

    fig.suptitle("Where the world's livestock numbers come from",
                 x=0.045, y=0.982, ha='left', fontsize=18, color='#141618')
    fig.text(0.045, 0.954,
             f'National livestock head counts reported to the FAO for {YEAR}, by how each '
             f'figure was obtained.',
             fontsize=11, color='#5A6167', ha='left')

    # Filter on recency, not size. A size threshold wrongly admitted a 2006 figure from an
    # overseas department and dropped Cyprus and Malta, whose flocks are small but current.
    gaps = gap_countries(df, 'Chickens')
    eu = gaps[gaps['nearest_year'] >= 2015]

    # The small-country claim is COMPUTED here rather than asserted, and exported, because a
    # figure printed on a chart with no artefact behind it is the thing this project exists
    # to object to. Rendered area is the projected polygon area scaled to the panel.
    panel_w_in = 13.5 * 0.475
    px_per_m = (panel_w_in * DPI) / (geo.total_bounds[2] - geo.total_bounds[0])
    small = geo.copy()
    small['px2'] = small.geometry.area * px_per_m ** 2
    cat = d[d['Item'] == 'Cattle'][['m49', 'Flag']]
    sm = small[['m49', 'NAME', 'px2']].merge(cat, on='m49', how='inner')
    tiny = sm[sm['px2'] < 64]
    big = sm[sm['px2'] >= 64]
    pct_tiny = (tiny['Flag'] == 'I').mean() * 100
    pct_big = (big['Flag'] == 'I').mean() * 100
    sm.sort_values('px2').to_csv('out/small-countries-2022.csv', index=False)
    print(f'small-country check: {len(tiny)} cattle areas render under 8x8 px, '
          f'{pct_tiny:.0f} per cent imputed, against {pct_big:.0f} per cent for the rest')
    import textwrap
    note = [
        'Source: FAOSTAT Production Crops and Livestock, release 2025-12-31, observation status '
        'flags. Equal Earth projection. Standing head counts for five species, not all farmed '
        'animals and not animals slaughtered.',
        f'{len(eu)} states filed no {YEAR} chicken count and the FAO did not impute one, so about '
        f'{eu["head"].sum()/1e6:.0f} million chickens, 2.3 per cent of the FAO world total, sit '
        'outside this figure. Including them at their nearest reported values, all official, '
        'raises the chicken share to 52 per cent.',
        f'{YEAR} is the most recent substantially filed year and is still being revised upward as '
        'countries report, so these shares are lower bounds. Of the cattle-reporting areas, the '
        f'{len(tiny)} that render smaller than eight pixels square are imputed {pct_tiny:.0f} per cent '
        f'of the time against {pct_big:.0f} per cent for the rest, so this map understates the gap.',
        'The same flags are published per country and per species by the GBADs FAOSTAT Data '
        'Visualizer. I could not find published work that maps them globally or weights them by '
        'animal population.',
    ]
    wrapped = '\n'.join(textwrap.fill(p, width=170) for p in note)
    fig.text(0.045, 0.012, wrapped, fontsize=7.6, color='#6F767C', ha='left',
             linespacing=1.5)

    fig.subplots_adjust(left=0.045, right=0.975, top=0.875, bottom=0.135,
                        wspace=0.03, hspace=0.155)
    fig.savefig('out/map-2022.png', dpi=DPI, facecolor='white')
    print('wrote out/map-2022.png')

    # Export what was actually DRAWN, geometry by geometry, so the picture can be diffed
    # against the source rather than trusted. This is the file that makes the Taiwan class
    # of defect visible: a geometry carrying a flag its own source row does not have.
    drawn = []
    for sp in CORE:
        s = d[d['Item'] == sp][['m49', 'Area', 'Flag', 'head']]
        m = geo[['m49', 'NAME', 'UN_A3']].merge(s, on='m49', how='left')
        m['species'] = LABEL.get(sp, sp)
        m['rendered_as'] = m['Flag'].fillna('none')
        drawn.append(m)
    dr = pd.concat(drawn, ignore_index=True).rename(
        columns={'NAME': 'geometry_name', 'Area': 'fao_area', 'UN_A3': 'ne_un_a3'})
    dr.to_csv('out/map-2022-drawn.csv', index=False)
    named = dr[dr['fao_area'].notna()]
    print(f"drawn export: {len(dr)} geometry-species rows, "
          f"{int(named['geometry_name'].nunique())} geometries carrying a flag")

    cv = pd.DataFrame(cover)
    cv.to_csv('out/map-2022-coverage.csv', index=False)
    print()
    print(cv.to_string(index=False))
    print(f'\nStates with no {YEAR} chicken figure but a chicken series elsewhere:')
    print(gaps.to_string(index=False))


def card(species='Chickens', out='out/map-card.png'):
    """A 16:10 single-species image for the website's project card.

    The five-panel figure is 2227 by 2128, near square. Dropped into the card's 16:10
    well with object-fit:cover it loses 34.7 per cent of its height, which cuts the top
    row of maps and slices the footnote mid-sentence. Cropping a research figure to fit
    a card is the wrong repair: the card wants one legible map, not a third of five.

    Chickens because they are 83.9 per cent of the animals and carry the finding. No
    title and no legend: the card supplies its own heading, and a legend at card size
    would be unreadable.
    """
    geo = load_geo()
    _, d = load_flags()
    s = d[d['Item'] == species][['m49', 'Flag']]
    m = geo.merge(s, on='m49', how='left')
    assert len(m) == len(geo), 'card merge changed the row count'

    fig, ax = plt.subplots(figsize=(16, 10))
    ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                           facecolor=SEA, edgecolor='none', zorder=-1))
    edges = m['Flag'].notna().map({True: 'white', False: NOROW_EDGE})
    widths = m['Flag'].notna().map({True: 0.18, False: 0.45})
    m.plot(ax=ax, color=m['Flag'].map(COLOURS).fillna(NOROW),
           edgecolor=edges.tolist(), linewidth=widths.tolist())
    ax.set_axis_off()
    ax.margins(0.01)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    # No bbox_inches='tight': it trims to the map's own 2.05:1 extent and throws the
    # 16:10 away, which is the whole point of this render. The world is centred in the
    # frame instead and the spare band above and below is paper, which is also the sea,
    # so the letterboxing is invisible rather than a margin.
    fig.savefig(out, dpi=100, facecolor=SEA)
    plt.close(fig)

    from PIL import Image
    w, h = Image.open(out).size
    print(f'wrote {out}  {w}x{h}  ratio {w / h:.3f} (the well is 1.600)')
    return out


if __name__ == '__main__':
    main()
