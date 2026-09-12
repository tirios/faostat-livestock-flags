"""Export chart-ready CSVs from out/numbers.json, and from nothing else.

Every figure a chart prints must come from the single source file, so a designer can be
handed these CSVs and no number is ever retyped. If a chart needs a quantity that is not
here, add it to make_numbers.py first; do not compute it in the chart.

Run: .venv/Scripts/python src/chart_data.py
Out: out/charts/*.csv and out/charts/source.json
"""

import csv
import json
import os

N = json.load(open('out/numbers.json', encoding='utf-8'))
OUT = 'out/charts'
os.makedirs(OUT, exist_ok=True)

FLAG_LABEL = {'A': 'Official national figure', 'E': 'Country estimate',
              'I': 'FAO imputed', 'X': 'External organisation'}


def write(name, rows, cols):
    path = f'{OUT}/{name}'
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f'wrote {path}  ({len(rows)} rows)')


def main():
    h = N['headline']

    # Headline split, animal-weighted, four flag classes. Must sum to 100 at the source's
    # own precision; a chart that prints 55 / 9 / 36 / 0.4 and sums to 100.4 is the map's
    # current headline-box defect, and the fix is to print what this file holds.
    split = [('A', h['pct_official']), ('E', h['pct_country_estimate']),
             ('I', h['pct_fao_imputed']), ('X', h['pct_external'])]
    assert abs(sum(v for _, v in split) - 100) < 0.05, split
    write('headline-2022.csv',
          [{'flag': f, 'label': FLAG_LABEL[f], 'pct_of_head': v} for f, v in split],
          ['flag', 'label', 'pct_of_head'])

    # Per species. share_of_set_pct is read, not derived: it was added to make_numbers.py
    # for exactly this file, and the chickens value must agree with the headline key.
    sp_rows = []
    for sp in h['species']:
        b = N['by_species'][sp]
        sp_rows.append({'species': sp, 'head': int(b['head']),
                        'head_millions': b['head_millions'], 'head_billions': b['head_billions'],
                        'share_of_set_pct': b['share_of_set_pct'],
                        'pct_official_by_head': b['pct_official_by_head'],
                        'pct_official_by_area': b['pct_official_by_area'],
                        'reporting_areas': b['reporting_areas'],
                        'fao_world_row': None if b['fao_world_row'] is None else int(b['fao_world_row']),
                        'pct_diff_vs_fao_world': b['pct_diff_vs_fao_world']})
    assert N['by_species']['Chickens']['share_of_set_pct'] == h['chickens_share_of_set']
    assert abs(sum(r['share_of_set_pct'] for r in sp_rows) - 100) < 0.2
    write('species-2022.csv', sp_rows, list(sp_rows[0].keys()))

    # Where the imputation is: the three largest imputed rows, then the with/without pair.
    c = N['concentration']
    top = [{'rank': i + 1, 'area': r['area'], 'species': r['species'], 'head': int(r['head']),
            'head_billions': r['head_billions'], 'pct_of_imputed': r['pct_of_imputed']}
           for i, r in enumerate(c['top3'])]
    assert all(top[i]['pct_of_imputed'] >= top[i + 1]['pct_of_imputed'] for i in range(len(top) - 1))
    write('concentration-2022.csv', top, list(top[0].keys()))
    write('concentration-excluding-china-2022.csv', [
        {'scenario': 'All five species', 'pct_official': h['pct_official'],
         'pct_imputed': h['pct_fao_imputed']},
        {'scenario': 'Excluding China mainland chickens',
         'pct_official': c['excluding_china_chickens']['pct_official'],
         'pct_imputed': c['excluding_china_chickens']['pct_imputed']},
    ], ['scenario', 'pct_official', 'pct_imputed'])

    # Australia, the worked example: one flag per species in the map year.
    au = N['australia']
    write('australia-2022.csv',
          [{'species': sp, 'head': int(au[sp]['head']), 'flag': au[sp]['flag'],
            'label': FLAG_LABEL[au[sp]['flag']]} for sp in h['species']],
          ['species', 'head', 'flag', 'label'])

    # Small-country bias, measured on cattle only. The 'rest' group size is not in the
    # source file and is therefore not printed here; say 'the remaining areas' in prose.
    s = N['small_country_bias']
    write('small-country-bias-2022.csv', [
        {'group': f'renders smaller than {int(s["threshold_px2"] ** 0.5)} by {int(s["threshold_px2"] ** 0.5)} px',
         'species': s['species'],
         'areas_in_group': s['areas_under_threshold'], 'areas_total': s['areas'],
         'pct_imputed': s['pct_imputed_under_threshold']},
        {'group': 'remaining areas', 'species': s['species'], 'areas_in_group': '',
         'areas_total': s['areas'], 'pct_imputed': s['pct_imputed_rest']},
    ], ['group', 'species', 'areas_in_group', 'areas_total', 'pct_imputed'])

    # Reporting lag at the key years the source file carries. The full annual series is
    # out/reporting-lag.csv, written by src/lag_panel.py; use that for a line chart.
    lag = [{'year': int(y), **{k: v for k, v in N['lag'][y].items()}} for y in sorted(N['lag'])]
    write('reporting-lag-keyyears.csv', lag, list(lag[0].keys()))

    # Reconciliation to the FAO's own World rows, to the head.
    r = N['reconciliation']
    write('reconciliation-2022.csv',
          [{'species': sp, 'head_difference_vs_fao_world': int(r['head_difference_vs_fao_world'][sp]),
            'exact_to_the_head': sp in r['species_exact_to_the_head']} for sp in h['species']],
          ['species', 'head_difference_vs_fao_world', 'exact_to_the_head'])

    # Provenance a designer needs for the source note, verbatim from the file.
    src = N['source']
    json.dump({'year': h['year'], 'species': h['species'], 'total_head': int(h['total_head']),
               'database': src['database'], 'release': src['release'], 'url': src['url'],
               'licence': src['licence'], 'archive_sha256': src['archive_sha256'],
               'fetched': src['fetched'], 'geometry': src['geometry'],
               'chicken_gap_states': r['chicken_gap_states'],
               'chicken_gap_head_millions': r['chicken_gap_head_millions'],
               'chicken_shortfall_pct': r['chicken_shortfall_pct'],
               'chicken_pct_official_including_gap': r['chicken_pct_official_including_gap'],
               'generated_from': 'out/numbers.json by src/chart_data.py'},
              open(f'{OUT}/source.json', 'w', encoding='utf-8'), indent=1)
    print(f'wrote {OUT}/source.json')


if __name__ == '__main__':
    main()
