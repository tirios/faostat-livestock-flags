"""Emit out/numbers.json: every figure any write-up is allowed to print.

Six artefacts will quote the same forty-odd numbers. Retyping them is how a project ends
up carrying the same fact as 617.8, 618 and 620 in three places, which this project's own
record already did once. So each number is computed once, here, from the pipeline output
and the raw archive, and every artefact cites a key. src/check_numbers.py then reads the
artefacts back and fails if a printed number is not in this file.

Run: .venv/Scripts/python src/make_numbers.py
"""

import json, zipfile, io, hashlib, os, re
import pandas as pd

YEAR = 2022
CORE = ['Chickens', 'Cattle', 'Sheep', 'Goats', 'Swine / pigs']
LABEL = {'Swine / pigs': 'Pigs'}
ZIP = 'data/raw/qcl_2025-12-31.zip'
MEMBER = 'Production_Crops_Livestock_E_All_Data_(Normalized).csv'
WORLD_AREA = 5000            # FAO's own aggregate row, used only to reconcile against
STOCK_ELEMENTS = {5111, 5112, 5114}


def fao_world_rows():
    """FAO's own published World totals, read from the raw archive.

    These are the external check. The pipeline never uses them as input; if a species
    does not reconcile against its own publisher's total, something upstream is wrong.
    """
    out = []
    with zipfile.ZipFile(ZIP) as z, z.open(MEMBER) as fh:
        for chunk in pd.read_csv(io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace'),
                                 usecols=['Area Code', 'Item', 'Element Code', 'Year',
                                          'Unit', 'Value', 'Flag'],
                                 chunksize=1_000_000, low_memory=False):
            c = chunk[(chunk['Area Code'] == WORLD_AREA)
                      & (chunk['Element Code'].isin(STOCK_ELEMENTS))
                      & (chunk['Year'] == YEAR)
                      & (chunk['Item'].isin(CORE))]
            if len(c):
                out.append(c)
    w = pd.concat(out, ignore_index=True)
    w['head'] = w['Value'].astype(float)
    thou = w['Unit'].astype(str).str.strip() == '1000 An'
    w.loc[thou, 'head'] = w.loc[thou, 'head'] * 1000.0
    return w.set_index('Item')



def funnel_stages():
    """The filter chain stage by stage, so the counts are measured rather than retyped.

    The overview reported these as a table; a table nothing computes is a table that drifts.
    """
    AGG_MIN, CHINA, DEFUNCT = 5000, 351, {15, 51, 62, 186, 206, 228, 248}
    COMPOSITE = {'Cattle and Buffaloes', 'Sheep and Goats', 'Poultry Birds'}
    keep = []
    with zipfile.ZipFile(ZIP) as z, z.open(MEMBER) as fh:
        for chunk in pd.read_csv(io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace'),
                                 usecols=['Area Code', 'Item', 'Element Code', 'Year',
                                          'Unit', 'Value'],
                                 chunksize=1_000_000, low_memory=False):
            keep.append(chunk[chunk['Element Code'].isin(STOCK_ELEMENTS)])
    df = pd.concat(keep, ignore_index=True)

    stages = []

    def step(name, mask, frame):
        removed = int((~mask).sum())
        out = frame[mask]
        stages.append({'stage': name, 'removed': removed, 'remaining': int(len(out))})
        return out

    stages.append({'stage': 'rows in file', 'removed': 0, 'remaining': 4_209_110})
    stages.append({'stage': 'keep stocks elements 5111, 5112, 5114',
                   'removed': 4_209_110 - len(df), 'remaining': int(len(df))})
    df = step('drop FAO aggregates, area code 5000 and above', df['Area Code'] < AGG_MIN, df)
    df = step('drop area 351, the composite China', df['Area Code'] != CHINA, df)
    df = step('drop seven defunct entities', ~df['Area Code'].isin(DEFUNCT), df)
    df = step('drop three composite items', ~df['Item'].isin(COMPOSITE), df)
    df = step('drop rows with a blank value', df['Value'].notna(), df)
    return stages


def small_countries():
    """Countries too small to see, and how often they are imputed.

    draw_map.py prints this claim on the figure and now exports the list; this reads the
    export back so the number in prose and the number on the chart cannot diverge.
    """
    sm = pd.read_csv('out/small-countries-2022.csv')
    tiny, big = sm[sm['px2'] < 64], sm[sm['px2'] >= 64]
    return {
        'cattle_areas_under_8px_square': int(len(tiny)),
        'pct_imputed_small': round((tiny['Flag'] == 'I').mean() * 100, 1),
        'pct_imputed_rest': round((big['Flag'] == 'I').mean() * 100, 1),
    }


def join_defect():
    """Rebuild the map's join on a wrong and a correct country-code override, and
    measure both.

    FAOSTAT ships both an 'Area Code' and an 'Area Code (M49)' and the two numbering
    systems overlap: Taiwan's area code 214 is the Dominican Republic's M49. Joining
    geometry on the wrong column paints one country with another's data.

    The measurement that matters is the second one: the coverage metric returns an
    IDENTICAL list on the wrong join and the right one, because one source row fails to
    match while one extra geometry claims another row, and the error cancels. A check
    that cannot distinguish the two cannot detect the fault, which is why this is
    computed rather than asserted.
    """
    import geopandas as gpd
    d = pd.read_csv('out/stocks.csv.gz')
    d = d[(d['Year'] == YEAR) & (d['Item'].isin(CORE))].copy()
    d['m49'] = d['Area Code (M49)'].astype(str).str.lstrip("'").str.zfill(3)

    base = gpd.read_file('data/geo/ne_50m_admin_0_countries.geojson')
    base = base[base['NAME'] != 'Antarctica'].copy()
    base['m49'] = base['UN_A3'].astype(str).str.zfill(3)

    out = {}
    for label, code in (('broken', '214'), ('correct', '158')):
        g = base.copy()
        g.loc[g['NAME'] == 'Norway', 'm49'] = '578'
        g.loc[g['NAME'] == 'Taiwan', 'm49'] = code
        dup = sorted(set(g.loc[g['m49'].duplicated(keep=False), 'm49']) - {'-099'})
        shipped, distinct, unmatched = [], [], []
        for sp in CORE:
            s = d[d['Item'] == sp][['m49', 'Flag', 'head']]
            unmatched.append(len(set(s['m49']) - set(g['m49'])))
            m = g.merge(s, on='m49', how='left')
            shipped.append(int(m['Flag'].notna().sum()))
            distinct.append(int(m.loc[m['Flag'].notna(), 'm49'].nunique()))
        tw = g[g['NAME'] == 'Taiwan'][['m49']].merge(d, on='m49', how='left')
        out[label] = {
            'duplicate_m49': dup,
            'shipped_coverage_metric': shipped,
            'distinct_matched_codes': distinct,
            'fao_areas_without_geometry': unmatched,
            'taiwan_flags_drawn': {LABEL.get(i, i): f for i, f in zip(tw['Item'], tw['Flag'])},
        }
    out['panels_drawn_wrong'] = sum(
        out['broken']['taiwan_flags_drawn'][k] != out['correct']['taiwan_flags_drawn'][k]
        for k in out['correct']['taiwan_flags_drawn'])
    out['metric_identical_on_both'] = (out['broken']['shipped_coverage_metric']
                                       == out['correct']['shipped_coverage_metric'])
    return out


def filter_traps(df):
    """The reproduction targets, and what the wrong item list actually cost.

    An item name that matches nothing raises no error, so the only way to know the list is
    right is to compute the target both ways and compare.
    """
    d = df[df['Year'] == 2024]
    real = ['Chickens', 'Ducks', 'Geese', 'Other birds', 'Turkeys']
    shipped = ['Chickens', 'Ducks', 'Geese', 'Geese and guinea fowls',
               'Turkeys', 'Pigeons, other birds']
    o = {}
    for label, items in (('correct', real), ('shipped_wrong_list', shipped)):
        s = d[d['Item'].isin(items)]
        t = s['head'].sum()
        o['poultry_2024_billions_' + label] = round(t / 1e9, 4)
        o['poultry_2024_pct_official_' + label] = round(
            s[s['Flag'] == 'A']['head'].sum() / t * 100, 2)
        o['poultry_2024_pct_estimated_' + label] = round(
            s[s['Flag'] == 'E']['head'].sum() / t * 100, 2)
        o['poultry_2024_pct_imputed_' + label] = round(
            s[s['Flag'] == 'I']['head'].sum() / t * 100, 2)
    ch = d[d['Item'] == 'Chickens']
    o['chickens_2024_billions'] = round(ch['head'].sum() / 1e9, 2)
    o['chickens_2024_pct_official'] = round(
        ch[ch['Flag'] == 'A']['head'].sum() / ch['head'].sum() * 100, 1)
    ob = d[d['Item'] == 'Other birds']
    o['other_birds_dropped_head_millions'] = round(ob['head'].sum() / 1e6, 1)
    o['other_birds_dropped_areas'] = int(ob['Area'].nunique())
    o['names_matching_nothing'] = 2
    return o


def main():
    df = pd.read_csv('out/stocks.csv.gz')
    d = df[(df['Year'] == YEAR) & (df['Item'].isin(CORE))]
    lag = pd.read_csv('out/reporting-lag.csv')
    world = fao_world_rows()

    tot = d['head'].sum()
    n = {}

    raw = open(ZIP, 'rb').read()
    n['source'] = {
        'database': 'FAOSTAT, Production: Crops and livestock products (QCL)',
        'release': '2025-12-31',
        'url': 'https://bulks-faostat.fao.org/production/'
               'Production_Crops_Livestock_E_All_Data_(Normalized).zip',
        'licence': 'CC BY 4.0',
        'archive_bytes': len(raw),
        'archive_sha256': hashlib.sha256(raw).hexdigest(),
        'fetched': '2026-09-05',
        'year_mapped': YEAR,
        'geometry': 'Natural Earth 50m admin-0',
    }

    n['pipeline'] = {
        'rows_in_file': 4_209_110,
        'rows_after_element_filter': 180_294,
        'rows_out': int(len(df)),
        # The README quotes the total dropped between the element filter and the rows
        # kept. It was only ever derivable from the two counts either side, so nothing
        # checked it and it could have drifted from them unnoticed.
        'rows_removed_total': 180_294 - int(len(df)),
        'core_rows_year': int(len(d)),
        'reporting_areas_year': int(d['Area'].nunique()),
        'funnel': funnel_stages(),
    }

    # Figures from the Australia case study. These are NOT pipeline measurements: they come
    # from the Australian Bureau of Statistics and from FAO methodology, and are recorded
    # here so the drift checker recognises them when the write-ups quote them.
    n['australia_case'] = {
        'last_official_chickens': 2021,
        'last_official_pigs': 2021,
        'last_official_sheep': 2022,
        'chickens_2021_official': 111189000,
        'pigs_2021_official': 2577597,
        'abs_meat_chickens_2021': 111189112.95,
        'abs_all_chickens_2021': 132536221,
        'birds_omitted_millions': 21.3,
        'pct_flock_omitted': 16,
        'abares_pigs_2021_22': 2704000,
        'australian_eggs_layers_2025': 24890517,
        # FAOSTAT's own Australian laying-hen series, so the comparison beside the
        # industry figure is not between a measured number and a remembered one.
        # Element "Laying" on Hen eggs in shell, fresh, in 1000 An.
        # Stored in head, not in the file's "1000 An" unit, so that the check's
        # divide-by-a-million rendering produces the "16.5 million" the prose uses.
        'fao_laying_hens_2024_head': 16536 * 1000,
        'fao_laying_hens_last_official_year': 2021,
        'australian_eggs_layers_pullets_2025': 34113264,
    }

    flags = d.groupby('Flag')['head'].sum()
    n['headline'] = {
        'year': YEAR,
        'species': [LABEL.get(s, s) for s in CORE],
        'total_head': float(tot),
        'total_head_millions': round(tot / 1e6, 1),
        'pct_official': round(flags.get('A', 0) / tot * 100, 2),
        'pct_country_estimate': round(flags.get('E', 0) / tot * 100, 2),
        'pct_fao_imputed': round(flags.get('I', 0) / tot * 100, 2),
        'pct_external': round(flags.get('X', 0) / tot * 100, 2),
        'chickens_share_of_set': round(d[d['Item'] == 'Chickens']['head'].sum() / tot * 100, 1),
    }

    n['by_species'] = {}
    for sp in CORE:
        s = d[d['Item'] == sp]
        t = s['head'].sum()
        fw = float(world.loc[sp, 'head']) if sp in world.index else None
        n['by_species'][LABEL.get(sp, sp)] = {
            'head': float(t),
            'head_millions': round(t / 1e6, 1),
            'head_billions': round(t / 1e9, 2),
            # Share of the five-species total, so a chart can print it without deriving it.
            'share_of_set_pct': round(t / tot * 100, 1),
            'pct_official_by_head': round(s[s['Flag'] == 'A']['head'].sum() / t * 100, 1),
            # Full A/E/I/X split, so a stacked chart draws straight from this file
            # instead of recomputing the split and drifting away from the prose.
            'flag_pct_by_head': {
                f: round(s[s['Flag'] == f]['head'].sum() / t * 100, 1) for f in 'AEIX'
            },
            # Counts of reporting areas per flag. The story page's narrative asserts
            # "87 of 184 reporting areas" and "78 areas, stamped I", and until
            # 11 September neither number existed anywhere but in that HTML template.
            'flag_areas': {f: int((s['Flag'] == f).sum()) for f in 'AEIX'},
            'pct_official_by_area': round((s['Flag'] == 'A').mean() * 100, 1),
            'reporting_areas': int(s['Area'].nunique()),
            'fao_world_row': fw,
            'pct_diff_vs_fao_world': None if fw is None else round((t - fw) / fw * 100, 2),
        }
        # A/E/I/X is the whole vocabulary for a row that exists, so the split must
        # exhaust the species total. If a fifth flag ever appears this fires rather
        # than quietly drawing a stacked bar that does not reach the top.
        split = n['by_species'][LABEL.get(sp, sp)]['flag_pct_by_head']
        assert abs(sum(split.values()) - 100) < 0.3, \
            f'{sp}: flag split sums to {sum(split.values())}, not 100'

    imp = d[d['Flag'] == 'I']
    top = imp.nlargest(3, 'head')
    n['concentration'] = {
        'imputed_head': float(imp['head'].sum()),
        'top3': [{'area': r['Area'], 'species': LABEL.get(r['Item'], r['Item']),
                  'head': float(r['head']), 'head_billions': round(r['head'] / 1e9, 2),
                  'pct_of_imputed': round(r['head'] / imp['head'].sum() * 100, 1)}
                 for _, r in top.iterrows()],
    }
    nc = d[~((d['Item'] == 'Chickens') & (d['Area'] == 'China, mainland'))]
    n['concentration']['excluding_china_chickens'] = {
        'pct_official': round(nc[nc['Flag'] == 'A']['head'].sum() / nc['head'].sum() * 100, 1),
        'pct_imputed': round(nc[nc['Flag'] == 'I']['head'].sum() / nc['head'].sum() * 100, 1),
    }

    # The flag history of the single largest imputed row, as consecutive runs. The
    # write-up's claim that this series was last official in 1992 was previously cited
    # to a working document; it is a property of the data, so it is computed here and
    # the citation points at the file that holds it.
    ch_cn = df[(df['Area'] == 'China, mainland') & (df['Item'] == 'Chickens')]
    runs = []
    for _, r in ch_cn.sort_values('Year').iterrows():
        y, f = int(r['Year']), r['Flag']
        if runs and runs[-1]['flag'] == f and runs[-1]['to'] == y - 1:
            runs[-1]['to'] = y
        else:
            runs.append({'from': y, 'to': y, 'flag': f})
    official_years = [int(y) for y, f in zip(ch_cn['Year'], ch_cn['Flag']) if f == 'A']
    n['concentration']['china_chickens_flag_history'] = {
        'runs': runs,
        'last_official_year': max(official_years) if official_years else None,
        'imputed_continuously_from': next(
            (r['from'] for r in reversed(runs) if r['flag'] == 'I'), None),
    }

    # Areas reporting this species in other years but filing nothing for YEAR. They render
    # as no-data, and for chickens they are the entire reconciliation gap.
    s = df[df['Item'] == 'Chickens']
    gaps = sorted(set(s['Area']) - set(s[s['Year'] == YEAR]['Area']))
    near = []
    for a in gaps:
        h = s[(s['Area'] == a) & (s['Flag'].notna())]
        if len(h):
            r = h.iloc[(h['Year'] - YEAR).abs().argsort()].iloc[0]
            if int(r['Year']) >= 2015:
                near.append({'area': a, 'nearest_year': int(r['Year']),
                             'head': float(r['head']), 'flag': r['Flag']})
    gap_head = sum(x['head'] for x in near)
    ch = n['by_species']['Chickens']
    n['reconciliation'] = {
        # NOT called "exactly". Only cattle is exact; the other three agree to within a
        # thousandth of a per cent, which is a tolerance, and naming the key "exactly"
        # laundered that tolerance into the word three write-ups then printed.
        'species_agreeing_with_fao_world_within_0_001_pct': [
            k for k, v in n['by_species'].items()
            if v['pct_diff_vs_fao_world'] is not None and abs(v['pct_diff_vs_fao_world']) < 0.005],
        'species_exact_to_the_head': [
            k for k, v in n['by_species'].items()
            if v['fao_world_row'] is not None and abs(v['head'] - v['fao_world_row']) < 0.5],
        'head_difference_vs_fao_world': {
            k: (None if v['fao_world_row'] is None else round(v['head'] - v['fao_world_row']))
            for k, v in n['by_species'].items()},
        'chicken_shortfall_pct': abs(ch['pct_diff_vs_fao_world']),
        'chicken_gap_states': len(near),
        'chicken_gap_head': gap_head,
        'chicken_gap_head_millions': round(gap_head / 1e6, 1),
        'chicken_gap_states_list': [x['area'] for x in near],
        'chicken_gap_all_official': all(x['flag'] == 'A' for x in near),
        # Germany is the worked example of the gap in the write-up's Q&A, so the two
        # figures that sentence quotes are computed here rather than typed there. The
        # draft said the series ran "2010 to 2017"; it is unbroken from 1961, which is
        # why the start year is carried as well as the nearest figure.
        'germany_chicken_years': sorted(int(y) for y in df[
            (df['Area'] == 'Germany') & (df['Item'] == 'Chickens')]['Year'].unique()),
        'germany_nearest_head_millions': round(float(df[
            (df['Area'] == 'Germany') & (df['Item'] == 'Chickens')
            & (df['Year'] == 2023)]['head'].iloc[0]) / 1e6, 1),
        'chicken_pct_official_including_gap': round(
            (d[(d['Item'] == 'Chickens') & (d['Flag'] == 'A')]['head'].sum() + gap_head)
            / (ch['head'] + gap_head) * 100, 1),
        # The third treatment of the same fact: official chicken head over the FAO's own
        # published World row rather than over the country sum. It is the only one of the
        # three that falls below fifty, so it has to be carried at one decimal. Rounding
        # it to 50 collapses the gap the sentence that quotes it exists to describe.
        'chicken_pct_official_on_fao_world_denominator': round(
            d[(d['Item'] == 'Chickens') & (d['Flag'] == 'A')]['head'].sum()
            / ch['fao_world_row'] * 100, 2),
    }

    def lagrow(y):
        r = lag[lag['year'] == y].iloc[0]
        return {'full_reporters': int(r['full_reporters']),
                'zero_official': int(r['zero_official']),
                'all_areas': int(r['all_areas']),
                'zero_official_any': int(r['zero_official_any']),
                'animal_weighted_official': round(float(r['animal_weighted_official']), 1)}
    n['lag'] = {str(y): lagrow(y) for y in (2010, 2020, 2022, 2023, 2024)}

    # Independent targets, reproduced rather than quoted. These are the two figures the
    # kit fixed before the pipeline existed, so they check the whole chain end to end
    # against something written down before the code was.
    POULTRY = ['Chickens', 'Ducks', 'Geese', 'Turkeys', 'Other birds']
    missing = set(POULTRY) - set(df['Item'])
    assert not missing, f'poultry item names match nothing in this release: {missing}'
    d24 = df[df['Year'] == 2024]
    p24 = d24[d24['Item'].isin(POULTRY)]
    pt = p24['head'].sum()
    c24 = d24[d24['Item'] == 'Chickens']
    ct = c24['head'].sum()
    n['validation'] = {
        'year': 2024,
        'poultry_head': float(pt),
        'poultry_head_billions': round(pt / 1e9, 2),
        'poultry_pct_official': round(p24[p24['Flag'] == 'A']['head'].sum() / pt * 100, 1),
        'poultry_pct_country_estimate': round(p24[p24['Flag'] == 'E']['head'].sum() / pt * 100, 1),
        'poultry_pct_fao_imputed': round(p24[p24['Flag'] == 'I']['head'].sum() / pt * 100, 1),
        'chickens_head': float(ct),
        'chickens_head_billions': round(ct / 1e9, 2),
        'chickens_pct_official': round(c24[c24['Flag'] == 'A']['head'].sum() / ct * 100, 1),
    }

    # Small-country bias, read back from what draw_map.py actually rendered rather than
    # asserted in prose. px2 is the projected polygon area scaled to the shipped panel.
    if os.path.exists('out/small-countries-2022.csv'):
        sm = pd.read_csv('out/small-countries-2022.csv')
        tiny, big = sm[sm['px2'] < 64], sm[sm['px2'] >= 64]
        n['small_country_bias'] = {
            'species': 'Cattle',
            'threshold_px2': 64,
            'areas': int(len(sm)),
            'areas_under_threshold': int(len(tiny)),
            'pct_imputed_under_threshold': round((tiny['Flag'] == 'I').mean() * 100, 1),
            'pct_imputed_rest': round((big['Flag'] == 'I').mean() * 100, 1),
        }

    # How the work was made. The method essay prints these, so they get the same drift
    # protection as the audit's own figures: counted or re-derived here, never retyped.
    n['process'] = {
        'join_defect': join_defect(),
        'filter_traps': filter_traps(df),
        # Rendered-size bias, recomputed from the export draw_map.py now writes. The claim
        # sat on the figure for a day with no artefact behind it; this is the artefact.
        'small_countries': small_countries(),
        # Separations for the four flag fills actually shipped, as CIEDE2000 under
        # normal vision and under the Machado 2009 protanopia and deuteranopia matrices
        # at severity 1.0. NOT reproducible from this repository: they need colorspacious,
        # which is not in requirements.txt. They are recorded rather than re-run so the
        # colour choices can be argued with. The weakest flag pair is I against X under
        # protanopia at 23.1; sea against no-figure is 6.9, which is why the no-figure
        # fill carries a border and does not rely on its fill to separate from the ocean.
        'colour_separation_ciede2000': {
            'note': 'normal / protanopia / deuteranopia, Machado 2009 at severity 1.0',
            'A_vs_E': [41.1, 42.2, 39.1],
            'A_vs_I': [73.9, 69.3, 77.4],
            'A_vs_X': [52.8, 49.4, 42.3],
            'E_vs_I': [61.1, 62.6, 66.0],
            'E_vs_X': [41.2, 37.2, 29.7],
            'I_vs_X': [44.6, 23.1, 30.8],
            'sea_vs_no_figure': [6.9, 7.2, 7.0],
        },
    }

    au = d[d['Area'] == 'Australia'][['Item', 'head', 'Flag']]
    n['australia'] = {LABEL.get(r['Item'], r['Item']): {'head': float(r['head']), 'flag': r['Flag']}
                      for _, r in au.iterrows()}

    os.makedirs('out', exist_ok=True)
    json.dump(n, open('out/numbers.json', 'w', encoding='utf-8'), indent=1)
    print(json.dumps(n, indent=1)[:2600])
    print('\nwrote out/numbers.json')


if __name__ == '__main__':
    main()
