"""Fail if any write-up prints a number that out/numbers.json does not hold.

Six artefacts quote the same forty-odd figures. Retyping is how a project ends up carrying
one fact as 617.8, 618 and 620 in three places, which this one did until it was caught.
make_numbers.py computes each figure once; this reads the prose back and checks it.

The check is deliberately noisy in one direction and silent in the other: it reports every
number it cannot account for, and the author clears them. A number that is genuinely new
prose (a year, a page count, a percentage from a cited paper) is added to ALLOWED below
with a reason, so the exceptions are a visible list rather than a loosened rule.

Run:  .venv/Scripts/python src/check_numbers.py
Exit: 0 if every printed figure is accounted for, 1 otherwise.
"""

import json, re, sys, glob, os

NUM = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{2,})(?![\w])')

# Numbers that legitimately appear in prose and are not project measurements.
ALLOWED = {
    # The story page's headline counter starts at zero and animates up to the real
    # figure in script. The zero is a placeholder, not a claim.
    '0.00',
    # ---- figures from cited third parties -------------------------------------
    # Not project measurements, so numbers.json cannot hold them. Each was verified by
    # opening the source on 11 September 2026; the citation in the post is the record.
    '211', '259.6', '259,585,231', '259585231', '136',   # Stray Dog, State of the Movement 2024 [1]
    '5.9', '9.22', '1.54',                               # GBADs portal vs the pinned bulk [18]
    '2605.26340',                                        # arXiv identifier [16]
    # ---- figures measured from the session transcripts --------------------------
    # Real measurements, but of the build session rather than of the livestock data, so
    # they have no home in numbers.json. Sources 3 to 5 carry the method.
    '3,070', '3070', '96.3', '38',
    # ---- properties of the checking page itself ---------------------------------
    # out/eda.html states its own total on the page: "All 48 checks pass." Putting it in
    # numbers.json would be circular, since the page checks numbers.json.
    '48',
    # ---- quantities that are not measurements -----------------------------------
    '100',   # "row width is always 100 per cent", and "100 per cent Opus 5"
    '30',    # the Science One blog's publication day, 30 July 2026
    '2.7', '30.9',  # flag-era shares quoted in the Open items, a working note not the post
    # ---- colour separations, measured once and not recomputed -------------------
    # Measured with colorspacious, which is not a dependency, and recorded in a comment at
    # the top of src/draw_map.py. The README says plainly that these two are asserted
    # rather than checked. They are the only figures in the project with that status.
    '23.1', '6.9',
    # ---- values produced by the DELIBERATELY BROKEN build -----------------------
    # README documents what failure looks like, quoting the figures that
    # src/build_eda.py --break taiwan produces. They are wrong on purpose, so by
    # definition they are not in numbers.json and never should be.
    '5.35', '31,160.2', '31160.2', '74.7', '1.51',
    # calendar years and release dates
    *{str(y) for y in range(1960, 2031)},
    '2025-12-31', '2020-21', '2021-22', '2022-23', '2023-24', '2024-25', '2015-16',
    # FAO element and area codes, quoted when explaining the pipeline
    '5111', '5112', '5114', '5312', '5313', '5318', '5319', '5320', '5321', '5322',
    '5323', '5412', '5413', '5417', '5422', '5423', '5424', '5510', '5513',
    '351', '5000', '158', '214', '578', '304', '238', '254', '312', '474', '638',
    '41', '96', '128', '15', '51', '62', '186', '206', '228', '248',
    # licence and standard identifiers, HTTP status codes, hash and projection names
    '4.0', '49', '110', '3166', '256', '521', '401', '400', '404', '200',
    '545', '244', '1615', '1,615', '95', '99', '05', '06', '07', '08', '09',
    # panel and rendering constants quoted when explaining the figure
    '165', '64', '8x8',
    # DOI prefix and article numbers of the two cited Data Science Journal papers
    '10.5334', '044', '026',
    # ordinary small integers used as counts in sentences
    *{str(n) for n in range(0, 25)},
}


def load_expected():
    n = json.load(open('out/numbers.json', encoding='utf-8'))
    seen = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)):
            seen.update(renderings(float(o)))
        elif isinstance(o, str):
            seen.add(o)
    walk(n)
    return {s for s in seen if s}


def fmt(v):
    if v == int(v):
        return f'{int(v):,}'
    return f'{v:,.10g}'.rstrip('0').rstrip('.')


def renderings(f):
    """Every string a writer might reasonably use for one quantity.

    fmt() drops a trailing .0, so a figure that lands on a round number only ever
    produced "51", and prose printing the measured "51.0 per cent" was reported as
    unaccounted. That failure is invisible on any quantity with a real decimal, which
    is why it survived: 40.3 matched and 51.0 did not. Emit both forms.
    """
    out = set()
    for v in (f, round(f, 1), round(f, 2), round(f), f / 1e6, f / 1e9,
              round(f / 1e6, 1), round(f / 1e9, 1), round(f / 1e9, 2),
              round(f / 1e6), round(f / 1e9), abs(f), round(abs(f), 1)):
        s = fmt(v)
        out.add(s)
        out.add(s.replace(',', ''))
        if v == int(v):                      # the one-decimal rendering of a round value
            out.add(f'{int(v):,}.0')
            out.add(f'{int(v)}.0')
    return out


def strip(text):
    """Remove everything that is machinery rather than a claim."""
    # Ignore fenced code, inline code and HTML comments: those are machinery, not claims.
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'<style.*?</style>|<script.*?</script>', ' ', text, flags=re.S)
    # The built map pages carry the world as inline SVG, which is hundreds of
    # thousands of coordinates. None of it is a claim, and leaving it in would
    # bury the prose figures under noise, so the drawing goes before the check.
    text = re.sub(r'<svg.*?</svg>', ' ', text, flags=re.S)
    # Camera positions (data-zoom="1270,210,2.2"), font weights in a stylesheet
    # URL and other attribute values are machinery. Only the text between tags
    # makes a claim, so attributes go before the numerals are counted.
    text = re.sub(r'<[a-zA-Z][^>]*>', lambda m: re.sub(r'="[^"]*"', '=""', m.group(0)), text)
    # A numeric character reference is a glyph, not a figure: &#10227; is the reset
    # arrow on the zoom control, and read as a number it is an unaccounted 10,227.
    text = re.sub(r'&#x?[0-9a-fA-F]+;', ' ', text)

    # Section numbers are document structure, not claims: the numeral that opens a heading
    # and the "section 4.4" style cross-reference. Stripping them here rather than widening
    # ALLOWED keeps the check tight, because it removes only a numeral in a position where
    # no measurement can appear. A numbered artefact otherwise has to smuggle every one of
    # its own headings into the exceptions list.
    text = re.sub(r'(<h[1-6][^>]*>)\s*\d+(?:\.\d+)*\.?(?=\s)', r'\1', text)
    text = re.sub(r'(?m)^(#{1,6}\s+)\d+(?:\.\d+)*\.?(?=\s)', r'\1', text)
    text = re.sub(r'\b([Ss]ections?)\s+\d+(?:\.\d+)*', r'\1', text)
    # Same rule, one more position. The post's design pass moved the section numeral
    # out of the heading and into an eyebrow above it, and repeated it in the contents
    # rail, so "01" through "04" started reading as four unaccounted figures. A
    # generator that emits a numeral from document order marks it data-num, and only
    # the whole content of such an element is dropped: a numeral cannot be a claim in
    # a position whose entire content is generated from the order of the sections.
    text = re.sub(r'<([a-z]+)\b[^>]*\bdata-num=""[^>]*>\s*\d+(?:\.\d+)*\.?\s*</\1>', ' ', text)
    return text


def check(path, expected):
    text = strip(open(path, encoding='utf-8').read())

    unknown = []
    for m in NUM.finditer(text):
        raw = m.group(1)
        bare = raw.replace(',', '')
        if raw in ALLOWED or bare in ALLOWED:
            continue
        if raw in expected or bare in expected:
            continue
        ctx = text[max(0, m.start() - 45):m.end() + 45].replace('\n', ' ')
        unknown.append((raw, ' '.join(ctx.split())))
    return unknown


def examined(path):
    """How much prose this check actually reads from a file: (characters, figures).

    A file whose text is assembled by script at runtime yields almost nothing to a
    static reader, and reporting that as "clean" overstates it.
    """
    text = strip(open(path, encoding='utf-8').read())
    visible = ' '.join(re.sub(r'<[^>]+>', ' ', text).split())
    return len(visible), len(NUM.findall(visible))


def main():
    if not os.path.exists('out/numbers.json'):
        print('out/numbers.json missing; run src/make_numbers.py first')
        return 1
    expected = load_expected()

    # The BUILT artefacts are checked too. They were not, until 11 September, and the
    # story page is the piece a reader actually sees: ten figures in its narrative that
    # nothing had ever read back. A checker that skips the hero artefact while reporting
    # "every printed figure traces to numbers.json" is claiming more than it does.
    targets = sorted(set(glob.glob('docs/*.md') + glob.glob('docs/preprint/*.html')
                         + glob.glob('docs/*.html') + ['README.md']
                         + ['out/post.html', 'out/map-2022-story.html', 'out/map-2022.html']))
    # review/, plan/ and the design documents describe how the thing was built: file
    # sizes, opacities, tile dimensions. They make no claims about livestock, so they
    # are machinery like a code comment, not prose to be held to numbers.json.
    targets = [t for t in targets if os.path.exists(t)
               and 'review' not in t and 'plan' not in t and 'design' not in t]

    bad = 0
    for t in targets:
        unknown = check(t, expected)
        if unknown:
            bad += len(unknown)
            print(f'\n{t}: {len(unknown)} figures not in numbers.json')
            for raw, ctx in unknown[:20]:
                print(f'   {raw:>14}   ...{ctx}...')
            if len(unknown) > 20:
                print(f'   and {len(unknown) - 20} more')
        else:
            # Report HOW MUCH was examined, not just that nothing was wrong. The
            # figure page builds its legend, subtitle and note in script at runtime,
            # so a static reader sees about a hundred characters of it and returns a
            # clean that means almost nothing. Printing the size makes a vacuous pass
            # look vacuous instead of looking like a result.
            seen = examined(t)
            note = '  (almost no prose reaches this check)' if seen[1] < 5 else ''
            print(f'{t}: clean, {seen[0]} chars and {seen[1]} figures examined{note}')

    if bad:
        print(f'\nFAIL: {bad} printed figures are not accounted for. Either they are wrong, '
              f'or they belong in numbers.json, or they belong in the ALLOWED list with a reason.')
        return 1
    print('\nPASS: every printed figure traces to numbers.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
