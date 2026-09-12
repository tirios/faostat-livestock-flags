"""Build out/eda.html: a single self-contained page for checking the map against the source.

This is a verification instrument, not a dashboard. Its one job is to let a reader decide
whether out/map-2022.png faithfully represents FAOSTAT, and to show them where it does not.
Every panel is built around a defect it would expose, and every check on it has been seen
to fail once, because a check that has only ever been green is decoration.

The page carries the data with it. No server, no CDN, no fetch, no font, no chart library.
It opens by double-click and works offline.

Run:
    .venv/Scripts/python src/build_eda.py                 normal build
    .venv/Scripts/python src/build_eda.py --break taiwan  reinstate the join defect
    .venv/Scripts/python src/build_eda.py --break numbers  corrupt one head value
    .venv/Scripts/python src/build_eda.py --refresh       re-read the raw zip

Out: out/eda.html (and, on a break build, out/eda-break.html so the good page survives).

The raw archive is read once and cached under out/eda-cache/, because the dropped rows and
FAO's own World rows are not in out/stocks.csv.gz and the page needs both.

Every figure the page shows is recomputed in the browser from the embedded data and
compared against out/numbers.json, so the page can disagree with the file that produced
it. That is the point: a verification page that can only ever agree proves nothing.
"""

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import zipfile
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, 'data', 'raw', 'qcl_2025-12-31.zip')
MEMBER = 'Production_Crops_Livestock_E_All_Data_(Normalized).csv'
GEOJSON = os.path.join(ROOT, 'data', 'geo', 'ne_50m_admin_0_countries.geojson')
CACHE = os.path.join(ROOT, 'out', 'eda-cache')
TEMPLATE = os.path.join(ROOT, 'src', 'eda_template.html')

USECOLS = ['Area Code', 'Area Code (M49)', 'Area', 'Item Code', 'Item',
           'Element Code', 'Year', 'Unit', 'Value', 'Flag']

# Mirrors src/build_table.py exactly. If these drift apart the funnel on the page stops
# describing the table it is drawn beside, so the build asserts they agree.
STOCK_ELEMENTS = [5111, 5112, 5114]
UNITS = {5111: 'An', 5112: '1000 An', 5114: 'No'}
AGG_MIN = 5000
CHINA_COMPOSITE = 351
CHINA_PARTS = [41, 96, 128, 214]
DEFUNCT = [15, 51, 62, 186, 206, 228, 248]
COMPOSITE_ITEMS = ['Cattle and Buffaloes', 'Sheep and Goats', 'Poultry Birds']
WORLD_AREA = 5000

# Mirrors src/draw_map.py.
YEAR = 2022
CORE = ['Chickens', 'Cattle', 'Sheep', 'Goats', 'Swine / pigs']
LABEL = {'Swine / pigs': 'Pigs'}
NAME_M49 = {'Norway': '578', 'Taiwan': '158'}
BROKEN_NAME_M49 = {'Norway': '578', 'Taiwan': '214'}   # Taiwan's FAOSTAT area code, not its M49
SENTINEL = '-099'

FLAG_ORDER = 'AEIXM'
# The map's own wording. FAO's verbatim descriptions are read from the archive and shown
# beside these, so the page never puts words in the publisher's mouth.
FLAG_WORDS = {
    'A': 'Official national figure',
    'E': 'Country estimate',
    'I': 'FAO imputed',
    'X': 'External organisation',
    'M': 'Missing; the FAO says the value cannot exist',
}

FUNNEL_WHY = {
    'element': 'Stocks live under three element codes. 5111 is mammals only, so filtering on it '
               'alone silently drops about 27 billion chickens; 5112 carries poultry in thousands '
               'of head; 5114 is bee colonies.',
    'aggregate': 'FAO regional and economic aggregates. Leaving them in double-counts every '
                 'country inside them.',
    'china': 'Area 351 "China" is a composite of mainland, Hong Kong, Macao and Taiwan. All five '
             'codes sit below 5000, so the aggregate filter misses it. It adds about 5.35 billion '
             'phantom chickens.',
    'defunct': 'Entities carrying historical data only. None of them can report a 2022 figure.',
    'item': 'Item rows that are sums of other item rows in the same column. Keeping them '
            'double-counts cattle, sheep, goats and every bird.',
    'blank': 'Rows with no value. Every one carries flag M, which is the FAO saying the value '
             'cannot exist rather than that it is unknown.',
}


# ---------------------------------------------------------------------------
# Loading


def read_stock_rows(refresh=False):
    """Every stocks row in the release, plus the file's total row count.

    Cached, because the page needs the dropped rows and the World rows and neither is in
    out/stocks.csv.gz, and re-reading a 545 MB CSV on every rebuild is a tax on using the
    instrument.
    """
    pq = os.path.join(CACHE, 'stock_all.parquet')
    meta = os.path.join(CACHE, 'meta.json')
    if not refresh and os.path.exists(pq) and os.path.exists(meta):
        m = json.load(open(meta, encoding='utf-8'))
        print(f'cache hit           : {pq}')
        return pd.read_parquet(pq), m

    print('reading the raw archive (about fifteen seconds)')
    frames, rows_in = [], 0
    with zipfile.ZipFile(ZIP) as z:
        flags_csv = z.read('Production_Crops_Livestock_E_Flags.csv').decode('utf-8-sig')
        with z.open(MEMBER) as fh:
            reader = pd.read_csv(io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace'),
                                 usecols=USECOLS, chunksize=1_000_000, low_memory=False)
            for chunk in reader:
                rows_in += len(chunk)
                frames.append(chunk[chunk['Element Code'].isin(STOCK_ELEMENTS)])
    df = pd.concat(frames, ignore_index=True)

    fao_flags = {}
    for line in flags_csv.strip().splitlines()[1:]:
        code, _, desc = line.partition(',')
        fao_flags[code.strip()] = desc.strip()

    m = {'rows_in_file': int(rows_in), 'fao_flag_descriptions': fao_flags}
    os.makedirs(CACHE, exist_ok=True)
    df.to_parquet(pq, index=False)
    json.dump(m, open(meta, 'w', encoding='utf-8'), indent=1)
    print(f'rows in file        : {rows_in:,}')
    return df, m


def build_funnel(stock):
    """Run build_table.py's filters in its order, keeping what each stage removed.

    build_table.py prints one 'dropped' total. The stage-by-stage counts only exist here,
    which is why the page is the first place the funnel can be inspected. The counts are
    sequential: a row removed as an aggregate is not counted again as a composite item.
    """
    d = stock.copy()
    d['head'] = d['Value'].astype(float)
    thou = d['Unit'].astype(str).str.strip() == '1000 An'
    d.loc[thou, 'head'] = d.loc[thou, 'head'] * 1000.0

    stages = [
        ('aggregate', 'Aggregate areas', 'Area Code >= 5000', d['Area Code'] >= AGG_MIN),
        ('china', 'China composite', f'Area Code == {CHINA_COMPOSITE}',
         d['Area Code'] == CHINA_COMPOSITE),
        ('defunct', 'Defunct entities', f'Area Code in {DEFUNCT}', d['Area Code'].isin(DEFUNCT)),
        ('item', 'Composite items', 'Item in ' + ', '.join(COMPOSITE_ITEMS),
         d['Item'].isin(COMPOSITE_ITEMS)),
        ('blank', 'Blank value', 'Value is empty', d['head'].isna()),
    ]

    ledger = [{'key': 'file', 'label': 'Rows in the release file', 'rule': 'no filter',
               'why': 'FAOSTAT QCL normalised, every element and every item.',
               'removed': None, 'remaining': None},
              {'key': 'element', 'label': 'Stocks rows', 'rule': 'Element Code in 5111, 5112, 5114',
               'why': FUNNEL_WHY['element'], 'removed': None, 'remaining': int(len(d))}]

    cur = d
    dropped = []
    for key, label, rule, mask in stages:
        m = mask.reindex(cur.index)
        gone = cur[m].copy()
        gone['reason'] = key
        dropped.append(gone)
        cur = cur[~m]
        ledger.append({'key': key, 'label': label, 'rule': rule, 'why': FUNNEL_WHY[key],
                       'removed': int(m.sum()), 'standalone': int(mask.sum()),
                       'remaining': int(len(cur))})
    ledger.append({'key': 'out', 'label': 'Rows out', 'rule': 'kept', 'why': 'out/stocks.csv.gz',
                   'removed': None, 'remaining': int(len(cur))})

    return cur, pd.concat(dropped, ignore_index=True), ledger


def read_geo(broken=False):
    """Natural Earth attributes only. No geometry is needed to audit an attribute join."""
    gj = json.load(open(GEOJSON, encoding='utf-8'))
    rows = []
    for f in gj['features']:
        p = f['properties']
        if p.get('NAME') == 'Antarctica':
            continue          # draw_map.py drops it, and it carries no FAO row
        rows.append({'NAME': p.get('NAME'), 'ADMIN': p.get('ADMIN'), 'ISO_A3': p.get('ISO_A3'),
                     'UN_A3': str(p.get('UN_A3')), 'TYPE': p.get('TYPE'),
                     'CONTINENT': p.get('CONTINENT')})
    g = pd.DataFrame(rows)
    g['m49_raw'] = g['UN_A3'].str.zfill(3)
    g['m49'] = g['m49_raw']
    override = BROKEN_NAME_M49 if broken else NAME_M49
    for name, code in override.items():
        n = int((g['NAME'] == name).sum())
        assert n == 1, f'expected exactly one {name} geometry, found {n}'
        g.loc[g['NAME'] == name, 'm49'] = code
    g['overridden'] = g['NAME'].isin(override)
    return g


def drawn_frame(geo, kept):
    """Rebuild what draw_map.py paints, geometry by geometry, from the same inputs.

    On a normal build this must reproduce out/map-2022-drawn.csv exactly. If it does not,
    the page's model of the join has drifted from the map's and nothing below it can be
    trusted, so the build says so loudly.
    """
    d = kept[(kept['Year'] == YEAR) & (kept['Item'].isin(CORE))].copy()
    d['m49'] = d['Area Code (M49)'].astype(str).str.lstrip("'").str.zfill(3)
    out = []
    for sp in CORE:
        s = d[d['Item'] == sp][['m49', 'Area', 'Flag', 'head']]
        m = geo[['m49', 'NAME', 'UN_A3']].merge(s, on='m49', how='left')
        m['species'] = LABEL.get(sp, sp)
        m['rendered_as'] = m['Flag'].fillna('none')
        out.append(m)
    dr = pd.concat(out, ignore_index=True).rename(
        columns={'NAME': 'geometry_name', 'Area': 'fao_area', 'UN_A3': 'ne_un_a3'})
    return dr[['m49', 'geometry_name', 'ne_un_a3', 'fao_area', 'Flag', 'head',
               'species', 'rendered_as']]


# ---------------------------------------------------------------------------
# Encoding


def clean(o):
    """NaN and numpy types out, JSON in. A NaN silently becomes the token NaN, which is not
    JSON, and the page then fails to parse with no useful message."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if o is None:
        return None
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if hasattr(o, 'item'):
        try:
            return clean(o.item())
        except Exception:
            return str(o)
    return o


def columnar(df, area_ix, item_ix, with_reason=False):
    """Dictionary-coded parallel arrays. head is not stored: it is v times 1000 when the
    element is 5112 and v otherwise, and the page recomputes it, which is what makes the
    thousands trap visible instead of buried in the build."""
    elem_ix = {c: i for i, c in enumerate(STOCK_ELEMENTS)}
    out = {
        'a': [area_ix[c] for c in df['Area Code']],
        'i': [item_ix[c] for c in df['Item Code']],
        'y': [int(v) - 1961 for v in df['Year']],
        'e': [elem_ix[c] for c in df['Element Code']],
        'v': [None if pd.isna(v) else round(float(v), 6) for v in df['Value']],
        'f': [FLAG_ORDER.index(f) if isinstance(f, str) and f in FLAG_ORDER else -1
              for f in df['Flag']],
    }
    if with_reason:
        keys = ['aggregate', 'china', 'defunct', 'item', 'blank']
        out['r'] = [keys.index(r) for r in df['reason']]
    return out


# ---------------------------------------------------------------------------
# Build


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--break', dest='brk', nargs='?', const='taiwan', default=None,
                    choices=['taiwan', 'numbers'],
                    help='build a deliberately broken page so the checks can be seen to fail')
    ap.add_argument('--refresh', action='store_true', help='re-read the raw archive')
    ap.add_argument('--out', default=None, help='output path')
    args = ap.parse_args()
    brk = args.brk

    os.chdir(ROOT)
    stock, meta = read_stock_rows(args.refresh)
    kept_recomputed, dropped, ledger = build_funnel(stock)

    # The shipped table is the record; the page describes it, so it reads it rather than a
    # recomputation. The recomputation still runs, to prove the funnel on the page is the
    # funnel that produced the file.
    kept = pd.read_csv('out/stocks.csv.gz')
    assert len(kept) == len(kept_recomputed), (
        f'funnel gives {len(kept_recomputed):,} rows, out/stocks.csv.gz holds {len(kept):,}; '
        'src/build_eda.py has drifted from src/build_table.py')

    if brk == 'numbers':
        # Corrupt exactly one embedded value: Brazil's 2022 cattle count, up ten per cent.
        m = ((kept['Area'] == 'Brazil') & (kept['Item'] == 'Cattle') & (kept['Year'] == YEAR))
        assert int(m.sum()) == 1, 'expected exactly one Brazil 2022 cattle row'
        before = float(kept.loc[m, 'Value'].iloc[0])
        kept.loc[m, 'Value'] = before * 1.1
        kept.loc[m, 'head'] = float(kept.loc[m, 'head'].iloc[0]) * 1.1
        print(f'BREAK numbers       : Brazil 2022 cattle {before:,.0f} -> {before * 1.1:,.0f}')

    geo = read_geo(broken=(brk == 'taiwan'))
    if brk == 'taiwan':
        print("BREAK taiwan        : Taiwan geometry keyed on M49 '214' "
              "(the Dominican Republic's code)")

    drawn_rebuilt = drawn_frame(geo, kept)
    if brk is None:
        shipped = pd.read_csv('out/map-2022-drawn.csv')
        same = (len(shipped) == len(drawn_rebuilt)
                and (shipped['rendered_as'].tolist() == drawn_rebuilt['rendered_as'].tolist())
                and (shipped['geometry_name'].tolist()
                     == drawn_rebuilt['geometry_name'].tolist()))
        print(f'drawn frame matches out/map-2022-drawn.csv : {same}')
        assert same, ('the rebuilt drawn frame differs from out/map-2022-drawn.csv; '
                      'the page would be auditing a join the map did not perform')
        drawn = shipped[['m49', 'geometry_name', 'ne_un_a3', 'fao_area', 'Flag', 'head',
                         'species', 'rendered_as']].copy()
        drawn['m49'] = drawn['m49'].astype(str).str.zfill(3)
    else:
        drawn = drawn_rebuilt

    world = stock[stock['Area Code'] == WORLD_AREA].copy()

    # One shared area dictionary across kept, dropped and drawn, so an index means the same
    # thing everywhere on the page.
    codes = pd.concat([kept[['Area Code', 'Area Code (M49)', 'Area']],
                       dropped[['Area Code', 'Area Code (M49)', 'Area']]]).drop_duplicates(
        subset=['Area Code']).sort_values('Area Code')
    area_ix = {c: i for i, c in enumerate(codes['Area Code'])}
    items = pd.concat([kept[['Item Code', 'Item']],
                       dropped[['Item Code', 'Item']],
                       world[['Item Code', 'Item']]]).drop_duplicates(
        subset=['Item Code']).sort_values('Item Code')
    item_ix = {c: i for i, c in enumerate(items['Item Code'])}

    data = {
        'meta': {
            'built': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'break': brk,
            'year': YEAR,
            'core': [LABEL.get(s, s) for s in CORE],
            'core_source': CORE,
            'rows_in_file': meta['rows_in_file'],
            'manifest': json.load(open('data/raw/manifest.json', encoding='utf-8')),
            'geometry': 'Natural Earth 50m admin-0, Antarctica dropped',
            'sentinel': SENTINEL,
            'overrides': BROKEN_NAME_M49 if brk == 'taiwan' else NAME_M49,
            'china_parts': CHINA_PARTS,
            'defunct': DEFUNCT,
            'composite_items': COMPOSITE_ITEMS,
            'elements': STOCK_ELEMENTS,
            'units': [UNITS[c] for c in STOCK_ELEMENTS],
        },
        'flagOrder': FLAG_ORDER,
        'flagWords': FLAG_WORDS,
        'faoFlags': meta['fao_flag_descriptions'],
        'area': {
            'code': [int(c) for c in codes['Area Code']],
            'name': list(codes['Area']),
            'm49': [str(x).lstrip("'").zfill(3) for x in codes['Area Code (M49)']],
        },
        'item': {'code': [int(c) for c in items['Item Code']], 'name': list(items['Item'])},
        'kept': columnar(kept, area_ix, item_ix),
        'drop': columnar(dropped, area_ix, item_ix, with_reason=True),
        'dropReasons': [
            {'key': 'aggregate', 'label': 'Aggregate area'},
            {'key': 'china', 'label': 'China composite 351'},
            {'key': 'defunct', 'label': 'Defunct entity'},
            {'key': 'item', 'label': 'Composite item'},
            {'key': 'blank', 'label': 'Blank value'},
        ],
        'world': {
            'i': [item_ix[c] for c in world['Item Code']],
            'y': [int(v) - 1961 for v in world['Year']],
            'e': [STOCK_ELEMENTS.index(c) for c in world['Element Code']],
            'v': [None if pd.isna(v) else float(v) for v in world['Value']],
            'f': [FLAG_ORDER.index(f) if isinstance(f, str) and f in FLAG_ORDER else -1
                  for f in world['Flag']],
        },
        'funnel': ledger,
        'geo': [{'n': r.NAME, 'ad': r.ADMIN, 'iso': r.ISO_A3, 'un': r.UN_A3,
                 'm49': r.m49, 'ty': r.TYPE, 'ct': r.CONTINENT, 'ov': bool(r.overridden)}
                for r in geo.itertuples()],
        'drawn': [{'m': r.m49, 'g': r.geometry_name, 'un': str(r.ne_un_a3),
                   'fa': None if pd.isna(r.fao_area) else r.fao_area,
                   'fl': None if pd.isna(r.Flag) else r.Flag,
                   'h': None if pd.isna(r.head) else float(r.head),
                   'sp': r.species}
                  for r in drawn.itertuples()],
        'coverage': pd.read_csv('out/map-2022-coverage.csv').to_dict('records'),
        'lag': pd.read_csv('out/reporting-lag.csv').to_dict('records'),
        'species22': pd.read_csv('out/species-2022.csv').to_dict('records'),
        'numbers': json.load(open('out/numbers.json', encoding='utf-8')),
    }

    blob = json.dumps(clean(data), separators=(',', ':'), allow_nan=False)
    blob = blob.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

    html = open(TEMPLATE, encoding='utf-8').read()
    assert '/*__DATA__*/null' in html, 'template has lost its data placeholder'
    html = html.replace('/*__DATA__*/null', blob)

    out = args.out or ('out/eda.html' if brk is None else 'out/eda-break.html')
    os.makedirs('out', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)

    size = os.path.getsize(out)
    print(f'\nkept rows           : {len(kept):,}')
    print(f'dropped rows        : {len(dropped):,}')
    print(f'world rows          : {len(world):,}')
    print(f'geometries          : {len(geo)}')
    print(f'drawn rows          : {len(drawn):,}')
    print(f'embedded data       : {len(blob) / 1e6:.2f} MB')
    print(f'wrote {out}         : {size:,} bytes ({size / 1e6:.2f} MB)')
    if brk:
        print(f'\nThis is a BREAK build ({brk}). Open it, read the check table, then delete it.')


if __name__ == '__main__':
    main()
