"""Build the filtered livestock stocks table from the FAOSTAT bulk download.

Every filter here exists because leaving it out produces a wrong number that looks
plausible and throws no error. The assertions at the end are the point: they must be
able to fail, so they are checked against known targets rather than against themselves.

Run:  python src/build_table.py
Out:  out/stocks.parquet, out/stocks.csv.gz, and a printed check report.
"""

import zipfile, io, sys
import pandas as pd

ZIP = 'data/raw/qcl_2025-12-31.zip'
MEMBER = 'Production_Crops_Livestock_E_All_Data_(Normalized).csv'

# Stocks elements. 5111 is mammals only (twelve items, NO birds); 5112 carries poultry
# in THOUSANDS of head; 5114 is bee colonies. Filtering on 5111 alone silently drops
# about 27 billion chickens.
STOCK_ELEMENTS = {5111, 5112, 5114}

# FAO regional and economic aggregates.
AGG_MIN = 5000

# Area 351 'China' is a composite of 41 (mainland), 96 (Hong Kong), 128 (Macao) and
# 214 (Taiwan). All five codes sit BELOW 5000, so the aggregate filter misses it.
CHINA_COMPOSITE = 351

# Entities carrying historical data only.
DEFUNCT = {15, 51, 62, 186, 206, 228, 248}

# Item rows that are sums of other item rows in the same column.
COMPOSITE_ITEMS = {'Cattle and Buffaloes', 'Sheep and Goats', 'Poultry Birds'}

USECOLS = ['Area Code', 'Area Code (M49)', 'Area', 'Item Code', 'Item',
           'Element Code', 'Element', 'Year', 'Unit', 'Value', 'Flag']


def load():
    frames = []
    rows_in = 0
    with zipfile.ZipFile(ZIP) as z:
        with z.open(MEMBER) as fh:
            reader = pd.read_csv(
                io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace'),
                usecols=USECOLS, chunksize=1_000_000, low_memory=False)
            for chunk in reader:
                rows_in += len(chunk)
                frames.append(chunk[chunk['Element Code'].isin(STOCK_ELEMENTS)])
    df = pd.concat(frames, ignore_index=True)
    print(f'rows in file        : {rows_in:,}')
    print(f'rows after element  : {len(df):,}')
    return df


def clean(df):
    n0 = len(df)

    # Units BEFORE anything else. 5112 is in thousands and the error is silent.
    unit_counts = df['Unit'].value_counts().to_dict()
    df = df.copy()
    df['head'] = df['Value'].astype(float)
    thou = df['Unit'].astype(str).str.strip() == '1000 An'
    df.loc[thou, 'head'] = df.loc[thou, 'head'] * 1000.0
    print(f'units seen          : {unit_counts}')
    print(f'rows scaled x1000   : {int(thou.sum()):,}')

    df = df[df['Area Code'] < AGG_MIN]
    df = df[df['Area Code'] != CHINA_COMPOSITE]
    df = df[~df['Area Code'].isin(DEFUNCT)]
    df = df[~df['Item'].isin(COMPOSITE_ITEMS)]
    df = df[df['head'].notna()]

    print(f'rows after cleaning : {len(df):,}  (dropped {n0 - len(df):,})')

    dupes = df.duplicated(subset=['Area Code', 'Item Code', 'Year'], keep=False).sum()
    print(f'duplicate keys      : {dupes:,}  (must be 0)')
    assert dupes == 0, 'country-species-year is not unique; investigate before continuing'
    return df


def check(df):
    """Reproduce known targets. These must be able to fail."""
    print('\n--- CHECKS ---')
    y = 2024
    d = df[df['Year'] == y]

    # The bird items actually present in this release. An earlier version of this list
    # carried 'Geese and guinea fowls' and 'Pigeons, other birds', which match nothing
    # here and silently dropped 'Other birds'. A name that matches nothing costs no error
    # and quietly changes the answer, so the list is asserted rather than trusted.
    poultry_items = ['Chickens', 'Ducks', 'Geese', 'Turkeys', 'Other birds']
    missing = set(poultry_items) - set(df['Item'])
    assert not missing, f'poultry item names match nothing in this release: {missing}'
    p = d[d['Item'].isin(poultry_items)]
    tot = p['head'].sum()
    print(f'{y} poultry head     : {tot/1e9:,.2f} bn   (target 28.75 bn)')
    print(f'{y} poultry countries: {p["Area"].nunique()}   (target 179)')
    fl = p.groupby('Flag')['head'].sum() / tot * 100
    print(f'{y} poultry flag %   : ' + ', '.join(f'{k} {v:.1f}' for k, v in fl.items()))
    print('                      (target A 42.4, E 17.6, I 40.0)')

    ch = d[d['Item'] == 'Chickens']
    cht = ch['head'].sum()
    cha = ch[ch['Flag'] == 'A']['head'].sum() / cht * 100
    print(f'{y} chickens         : {cht/1e9:,.2f} bn, {cha:.1f}% official'
          f'   (target 26.87 bn, 44.1%)')

    print(f'\n{y} animal-weighted official share by species:')
    for item in ['Swine / pigs', 'Pigs', 'Sheep', 'Cattle', 'Goats', 'Chickens', 'Ducks']:
        s = d[d['Item'] == item]
        if len(s) == 0:
            continue
        t = s['head'].sum()
        a = s[s['Flag'] == 'A']['head'].sum() / t * 100 if t else float('nan')
        print(f'  {item:<16} {t/1e6:10,.1f} M   {a:5.1f}% official')
    print('  (targets: pigs 89.1, sheep 55.0, cattle 50.2, goats 44.9, ducks 13.2)')

    # Reporting lag. The species set is FIXED and only countries reporting all five are
    # counted, because a mean over whatever a country happens to report rewards countries
    # farming few species: a country with three species all official scores 100 per cent.
    print('\nReporting lag, countries reporting ALL five core species:')
    core = ['Cattle', 'Sheep', 'Goats', 'Chickens', 'Swine / pigs']
    for yy in [2018, 2020, 2021, 2022, 2023, 2024]:
        dd = df[(df['Year'] == yy) & (df['Item'].isin(core))]
        n_sp = dd.groupby('Area')['Item'].nunique()
        full = n_sp[n_sp == len(core)].index
        per = dd[dd['Area'].isin(full)].groupby('Area')['Flag'].apply(lambda s: (s == 'A').mean())
        print(f'  {yy}: {int((per == 0).sum()):3d} of {per.size:3d} full reporters at zero official'
              f'   median official share {per.median()*100:5.1f}%')

    # Assertions, not prints. Each was checked against a deliberately broken input.
    ch24 = d[d['Item'] == 'Chickens']['head'].sum()
    assert 26e9 < ch24 < 27e9, f'world chickens {ch24:,.0f} outside 26 to 27 bn; check units and China 351'
    po24 = p['head'].sum()
    assert abs(po24 / 1e9 - 28.75) < 0.02, f'world poultry {po24/1e9:.4f} bn, target 28.75'
    assert len(df) == 104_089, f'{len(df):,} rows out, expected 104,089'
    print('\nassertions passed: chicken total, poultry total, row count')


if __name__ == '__main__':
    df = load()
    df = clean(df)
    check(df)
    import os
    os.makedirs('out', exist_ok=True)
    keep = ['Area Code', 'Area Code (M49)', 'Area', 'Item Code', 'Item',
            'Element Code', 'Year', 'Unit', 'Value', 'head', 'Flag']
    try:
        df[keep].to_parquet('out/stocks.parquet', index=False)
        print('\nwrote out/stocks.parquet')
    except ImportError:
        print('\nno parquet engine installed, writing csv.gz only')
    df[keep].to_csv('out/stocks.csv.gz', index=False, compression='gzip')
    print(f'wrote out/stocks.csv.gz  ({len(df):,} rows)')
