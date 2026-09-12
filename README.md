# FAOSTAT livestock observation-status flags, mapped and weighted by animal

Every livestock head count FAOSTAT publishes carries a one-letter flag saying where the
number came from:

| Flag | Meaning |
|---|---|
| `A` | an official national figure |
| `E` | the country's own estimate |
| `I` | a value the FAO imputed, because nobody filed one |
| `X` | a figure from an external organisation |
| `M` | missing |

This repository maps that flag for five species in one year, and weights it by how many
animals sit behind each category rather than by how many countries do.

That weighting is the point. Counting countries and counting animals give different
answers, because the species with the most animals is also the one fewest countries
count properly.

## What it finds

Of **31.1 billion** cattle, sheep, goats, pigs and chickens in 2022:

| | share of animals |
|---|---|
| behind an official national figure | **55.1%** |
| behind the country's own estimate | 8.8% |
| behind an FAO imputation | **35.7%** |
| behind an external organisation | 0.4% |

The average hides the spread. Row height in the chart is each species' share of the
total, which is why chickens dominate it:

| Species | Head | Share of the five | Official, by head | Reporting areas |
|---|---|---|---|---|
| Chickens | 26.11 bn | 83.9% | 51.0% | 184 |
| Cattle | 1.56 bn | 5.0% | 74.3% | 192 |
| Sheep | 1.35 bn | 4.3% | 76.7% | 180 |
| Goats | 1.14 bn | 3.6% | 63.9% | 187 |
| Pigs | 0.98 bn | 3.2% | 94.8% | 172 |

Chickens are 83.9 per cent of these animals and the least officially counted. Pigs are
the best counted and are about three per cent of the total.

The imputation is concentrated rather than spread. One row, China's mainland chicken
count at 5.19 billion birds, is **46.7 per cent of every imputed animal in the set**.
Remove that single row and the official share rises from 55.1 to 66.1 per cent. That
series was last flagged official in 1992; it has been imputed continuously since 2015
(`concentration.china_chickens_flag_history`).

A flag is a provenance label, not a quality score. An official figure can be a bad
census and an imputed figure can be close to the truth. Nothing here claims any imputed
number is wrong. It measures how much of the world total rests on a number nobody in
the country counted.

## Running it

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

.venv/Scripts/python src/make_numbers.py     # computes out/numbers.json
.venv/Scripts/python src/draw_map.py         # the five-panel figure
.venv/Scripts/python src/interactive_map.py  # the interactive map and scroll narrative
.venv/Scripts/python src/chart_species.py    # the stacked bar chart
.venv/Scripts/python src/lag_panel.py        # reporting lag over time
.venv/Scripts/python src/build_eda.py        # a page that recomputes 48 figures in the browser
.venv/Scripts/python src/check_numbers.py    # fails if any prose figure is not in numbers.json
```

## How it is kept honest

**Every figure is computed once.** `src/make_numbers.py` writes `out/numbers.json` and
nothing else is allowed to retype a number. `src/check_numbers.py` reads the prose back
and fails on any figure the file does not hold, so a number cannot drift between the
write-up, the README and the figures. Exceptions are a visible list with a stated reason,
not a loosened rule.

**The source is pinned.** `data/raw/manifest.json` records the SHA-256 of the archive,
and the archive is in the repository, because the FAO bulk endpoint serves only the
current release. Without the file the pin cannot be checked against anything.

**The checks are proven able to fail.** `src/build_eda.py --break taiwan` rebuilds the
verification page with a deliberately wrong country-code join, and eight of its rows go
red. A check that has only ever been green is decoration.

**One check is recorded as insufficient.** `process.join_defect` in `numbers.json` holds
the measurement that made the point. FAOSTAT ships both an `Area Code` and an
`Area Code (M49)`, and the two overlap: Taiwan's area code 214 is the Dominican
Republic's M49. Joining geometry on the wrong column paints one country with another's
data. The coverage metric written to catch exactly that returns an **identical** list on
the wrong join and the right one, because one source row fails to match while one extra
geometry claims another row and the error cancels. The defect is caught instead by three
assertions that do discriminate, in `src/draw_map.py`.

**Colour is checked, not asserted.** `process.colour_separation_ciede2000` records the
separation between every pair of flag colours under normal, protanopic and deuteranopic
vision. The weakest flag pair is `I` against `X` at 23.1. Sea against no-figure is 6.9,
which is why a country with no figure carries a border rather than relying on its fill.

## Layout

```
src/            the pipeline, one script per artefact
data/raw/       the pinned FAOSTAT archive and its SHA-256 manifest
data/geo/       Natural Earth 50m admin-0 boundaries
out/            everything the pipeline produces, including numbers.json
out/charts/     the same figures as CSV, for reuse without running anything
```

## Scope and limits

- **One year, five species.** 2022 is the most recent substantially filed year. It is
  still revised upward as countries report, so these shares are lower bounds.
- **Standing head counts**, not animals slaughtered, and not all farmed animals.
- **Ten states filed no 2022 chicken count** and the FAO imputed none, so about 618
  million birds, 2.3 per cent of the FAO world chicken total, sit outside the figure.
  Including them at their nearest reported values, all official, raises the chicken
  official share to 52 per cent. `reconciliation` carries the detail.
- **No uncertainty quantification.** Every quantity is a ratio of sums over observed
  rows, so there is no sampling, no parameter and nothing to put an interval on.
- **The small-country finding is measured on cattle only** and depends on the render
  resolution, which is why `DPI` in `src/draw_map.py` is not free to change.

## Source

FAO. 2025. *Production: Crops and livestock products*. FAOSTAT, release 2025-12-31.
Licence: CC BY 4.0. <https://www.fao.org/faostat/en/#data/QCL>

See `LICENSE` for terms: the code and derived outputs are CC0, the FAOSTAT archive
remains CC BY 4.0 and its attribution has to travel with it.
