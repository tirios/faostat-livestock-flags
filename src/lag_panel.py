"""The reporting-lag panel: how much of the most recent year is actually counted.

This needs no map geometry, so it runs today. It is the second panel of the artefact
and arguably the harder-hitting one: the most recent year of the world's main livestock
database is largely filled in by FAO rather than reported by countries.

Run: python src/lag_panel.py
Out: out/reporting-lag.png, out/species-2022.csv
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CORE = ['Cattle', 'Sheep', 'Goats', 'Chickens', 'Swine / pigs']
INK, MUTE, ACC = '#1a1a1a', '#8a8a8a', '#b4453c'

df = pd.read_csv('out/stocks.csv.gz')

years = list(range(2010, 2025))
rows = []
for y in years:
    d = df[(df['Year'] == y) & (df['Item'].isin(CORE))]
    if not len(d):
        continue

    # The denominator is FIXED to countries reporting all five species. A mean over
    # whatever a country happens to report rewards countries farming few species: three
    # species all official scores 100 per cent and outranks a country reporting fourteen.
    # The unfixed series is kept beside it so the difference is visible rather than
    # asserted, and because the unfixed level is the more alarming of the two.
    n_sp = d.groupby('Area')['Item'].nunique()
    full = n_sp[n_sp == len(CORE)].index
    per = d[d['Area'].isin(full)].groupby('Area')['Flag'].apply(lambda s: (s == 'A').mean())
    per_any = d.groupby('Area')['Flag'].apply(lambda s: (s == 'A').mean())

    tot = d['head'].sum()
    rows.append({
        'year': y,
        'full_reporters': per.size,
        'zero_official': int((per == 0).sum()),
        'pct_full_reporters_zero': (per == 0).mean() * 100,
        'median_share_full': per.median() * 100,
        'all_areas': per_any.size,
        'zero_official_any': int((per_any == 0).sum()),
        'pct_any_zero': (per_any == 0).mean() * 100,
        'animal_weighted_official': d[d['Flag'] == 'A']['head'].sum() / tot * 100,
    })
lag = pd.DataFrame(rows)
lag.to_csv('out/reporting-lag.csv', index=False)
print(lag.to_string(index=False))

fig, ax = plt.subplots(2, 1, figsize=(8, 6.4), sharex=True,
                       gridspec_kw={'hspace': 0.18})

ax[0].plot(lag['year'], lag['animal_weighted_official'], color=INK, lw=1.8,
           marker='o', ms=4)
ax[0].set_ylabel('per cent', color=INK, fontsize=9)
ax[0].set_title('Share of farmed animals whose head count is an official national figure',
                loc='left', fontsize=10.5, color=INK, pad=10)
ax[0].set_ylim(0, 100)

ax[1].plot(lag['year'], lag['pct_any_zero'], color='#c9a99a', lw=1.4, marker='o', ms=3,
           label='all reporting areas')
ax[1].plot(lag['year'], lag['pct_full_reporters_zero'], color=ACC, lw=1.8, marker='o', ms=4,
           label='areas reporting all five species')
ax[1].set_ylabel('per cent', color=INK, fontsize=9)
ax[1].set_title('Reporting areas filing no official figure at all, for any of the five species',
                loc='left', fontsize=10.5, color=INK, pad=10)
ax[1].set_ylim(0, 60)
ax[1].legend(frameon=False, fontsize=7.8, loc='upper left', labelcolor=MUTE)

for a in ax:
    a.spines[['top', 'right']].set_visible(False)
    a.spines[['left', 'bottom']].set_color(MUTE)
    a.tick_params(colors=MUTE, labelsize=8.5)
    a.grid(axis='y', color='#e8e8e8', lw=0.7)
    a.set_axisbelow(True)

last = lag.iloc[-1]
ax[1].annotate(f"{int(last['zero_official'])} of {int(last['full_reporters'])}",
               xy=(last['year'], last['pct_full_reporters_zero']),
               xytext=(-8, 8), textcoords='offset points',
               ha='right', fontsize=8.5, color=ACC)

fig.text(0.125, 0.015,
         'Cattle, sheep, goats, chickens and pigs. FAOSTAT stocks, release 2025-12-31. The lower panel '
         'fixes the denominator to areas\nreporting all five species, because a mean over whatever a '
         'country happens to report rewards those farming few species.\n'
         'The fall in the final year is reporting lag backfilled by FAO imputation, not a collapse in '
         'counting. Both series depend only\non the official flag, so neither crosses the 2015 break '
         'where the FAO reclassified its own estimated and imputed labels.',
         fontsize=7.2, color=MUTE, va='bottom')
fig.subplots_adjust(bottom=0.20, top=0.93, left=0.125, right=0.96)
fig.savefig('out/reporting-lag.png', dpi=170)
print('\nwrote out/reporting-lag.png')

# The year to map is 2022, so hand its species table over ready to use.
d22 = df[(df['Year'] == 2022) & (df['Item'].isin(CORE))]
sp = (d22.groupby('Item')
      .apply(lambda g: pd.Series({
          'head_millions': g['head'].sum() / 1e6,
          'pct_official': g[g['Flag'] == 'A']['head'].sum() / g['head'].sum() * 100,
          'countries': g['Area'].nunique()}), include_groups=False)
      .sort_values('head_millions', ascending=False))
sp.to_csv('out/species-2022.csv')
print('\n2022, the year to map:')
print(sp.round(1).to_string())
