"""Deterministic checks on Sprout's answers.

The system prompt already tells Sprout not to invent numbers, not to rename
categories and not to leak internal field names. Instructions are not evidence:
Sprout was caught in QA calling the "Other" category "World Foods", which the
prompt did not forbid at the time and no amount of re-reading the prompt would
have surfaced. This module is the part that can actually be checked.

Nothing here calls a model - it is pure string/number work, so it is cheap
enough to run on every answer and deterministic enough to assert on in tests.
Used by multi-agents/scripts/eval_goldenacre_sprout.py.

The hard one is figure grounding. A naive "is this substring in the context"
test is useless: Sprout writes "£19.76m" where the context holds 19756019.0.
So figures are parsed to numbers and matched against every number in the
context within a tolerance derived from how precisely they were written -
"£19.76m" must match to ~0.005m, "£20m" only to ~0.5m.
"""
import re

# Field, table and column names. Sprout is given these to ground its answer and
# must use them silently - a client reading "GA_BUYER" learns nothing.
BANNED_IDENTIFIERS = [
    "GA_BUYER", "AC_MANUFACTURER", "AC_BRAND", "GA_BRAND", "HC_MASTER",
    "REFERENCE_MATCH_STATUS", "portfolio_extras", "golden_acre_own_brands",
    "PERIOD_MATX", "VALUE_SALES", "UNIT_SALES", "sqlmesh", "TRANSFORM.",
]

# The three category names, exactly as the dashboard prints them. Anything else
# presented as a category name is a rename, however plausible it sounds.
CATEGORIES = {"halal", "polish", "other"}
CATEGORY_RENAMES = [
    "world foods", "world food", "general", "ambient", "everything else",
    "miscellaneous", "unclassified categories",
]

_MAGNITUDE = {"bn": 1e9, "b": 1e9, "m": 1e6, "k": 1e3, "": 1.0}

# "£19.76m", "£1.16bn", "£257,404", "45.8%", "+132.0%", "-3.6pp"
#
# (?![a-z]) on the magnitude is load-bearing. Without it, "£131,802 MAT" parses
# as £131,802 MILLION - the M of MAT read as a suffix - and the guard then
# reports a perfectly correct answer as an invented figure. Caught by the eval
# on its first run, against real output.
_FIGURE = re.compile(
    r"(?P<currency>£)?\s*(?P<sign>[+-])?(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<mag>bn|b|m|k)?(?![a-z])\s*(?P<unit>%|pp)?",
    re.IGNORECASE,
)


def _walk_numbers(obj):
    """Every number anywhere in the context, however deeply nested."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_numbers(v)


def parse_figures(text):
    """Figures a reader would take as factual claims, as (raw, value, kind)."""
    out = []
    for m in _FIGURE.finditer(text):
        raw = m.group(0).strip()
        num = m.group("num")
        if not num:
            continue
        mag = (m.group("mag") or "").lower()
        unit = (m.group("unit") or "").lower()
        currency = m.group("currency")
        if not currency and not unit and not mag:
            continue  # a bare number (a rank, a year, a count) - not a claim of scale
        try:
            value = float(num.replace(",", "")) * _MAGNITUDE.get(mag, 1.0)
        except ValueError:
            continue
        kind = "money" if currency else ("percent" if unit in ("%", "pp") else "number")
        decimals = len(num.split(".")[1]) if "." in num else 0
        out.append({"raw": raw, "value": value, "kind": kind,
                    "decimals": decimals, "magnitude": _MAGNITUDE.get(mag, 1.0)})
    return out


def _tolerance(fig):
    """How far off a match may be, given how precisely the figure was written.

    Half of the last written digit, so "£19.76m" allows ±0.005m and "£20m"
    allows ±0.5m. Anything tighter would flag ordinary rounding as invention.
    """
    step = fig["magnitude"] / (10 ** fig["decimals"])
    return max(step * 0.5, abs(fig["value"]) * 1e-9)


def ungrounded_figures(answer, context, extra_allowed=()):
    """Figures in the answer that match no number in the context.

    Sums and differences Sprout works out itself will show up here. That is
    intended: a derived number is exactly the kind that should be eyeballed,
    not waved through because it looked confident.
    """
    numbers = list(_walk_numbers(context)) + [float(x) for x in extra_allowed]
    # A percentage may be written 45.8 or stored 0.458; allow both readings.
    expanded = numbers + [n * 100 for n in numbers if abs(n) <= 1]
    # Match on MAGNITUDE, not signed value. Prose carries the direction - the
    # context stores -15.09 and a correct answer says "down 15.1%", which a
    # signed comparison flags as invented. Matching correct answers as failures
    # would make this whole check something people learn to ignore.
    #
    # The trade-off, stated plainly: this check verifies that a number is real,
    # NOT that its stated direction is right. "up 15.1%" against a -15.09
    # context passes here. Direction is covered by the eval's own assertions.
    magnitudes = {abs(n) for n in expanded}
    # The complement of a share is a legitimate, checkable derivation: with
    # 45.8% unmatched, "the ~54% that could be classified" is arithmetic, not
    # invention. Allowed for percentages ONLY, and only against 100. Broader
    # derivations (sums, ratios) still surface - those deserve a human eye.
    # Left too strict, this fires on almost every share answer, and a check
    # that cries wolf is one people stop reading.
    percent_extra = {100.0 - n for n in magnitudes if 0.0 <= n <= 100.0}
    out = []
    for fig in parse_figures(answer):
        tol = _tolerance(fig)
        candidates = magnitudes | (percent_extra if fig["kind"] == "percent" else set())
        if any(abs(abs(fig["value"]) - n) <= tol for n in candidates):
            continue
        out.append(fig)
    return out


def _brand_numbers(context):
    """brand name (lowercased) -> every number recorded against it.

    Figure grounding alone cannot catch a SWAP: "Najma £131.8k, Jaldee Eats
    £19.76m" quotes two figures that are both genuinely in the context, so
    every number reconciles while the answer is exactly wrong. This is what
    lets attribution be checked.
    """
    found = {}

    def add(name, numbers):
        if not name:
            return
        found.setdefault(str(name).strip().lower(), set()).update(
            n for n in numbers if isinstance(n, (int, float)) and not isinstance(n, bool)
        )

    def walk(obj, inherited_name=None):
        if isinstance(obj, dict):
            name = obj.get("brand") or obj.get("name") or inherited_name
            add(name, [v for v in obj.values() if isinstance(v, (int, float))])
            for k, v in obj.items():
                # keys like "najma" / "jaldee_eats" name the block beneath them
                walk(v, k.replace("_", " ") if isinstance(v, dict) and not obj.get("brand") else name)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v, inherited_name)

    walk(context)
    return {k: v for k, v in found.items() if v and len(k) > 2}


def misattributed_figures(answer, context):
    """Money figures attached to the wrong brand.

    A money figure is taken to belong to the nearest brand name mentioned
    before it, within 120 characters. Deliberately conservative: a figure with
    no brand nearby, or a brand with nothing recorded against it, is skipped
    rather than guessed at.
    """
    brands = _brand_numbers(context)
    if not brands:
        return []
    low = answer.lower()
    mentions = []
    for name in brands:
        for m in re.finditer(re.escape(name), low):
            mentions.append((m.start(), name))
    mentions.sort()
    if not mentions:
        return []

    out = []
    for m in _FIGURE.finditer(answer):
        if not m.group("currency"):
            continue
        figs = parse_figures(m.group(0))
        if not figs:
            continue
        fig = figs[0]
        pos = m.start()
        owner = None
        for start, name in mentions:
            if start < pos and pos - start <= 120:
                owner = name           # nearest preceding wins
        if owner is None:
            continue
        known = brands[owner]
        tol = _tolerance(fig)
        if any(abs(abs(fig["value"]) - abs(n)) <= tol for n in known):
            continue
        # only report when the figure IS a real number elsewhere in the context:
        # that is a swap. A wholly invented number is already reported as
        # ungrounded, and reporting it twice just doubles the noise.
        everywhere = {abs(n) for n in _walk_numbers(context)}
        if any(abs(abs(fig["value"]) - n) <= tol for n in everywhere):
            out.append({"brand": owner, "raw": fig["raw"]})
    return out


def leaked_identifiers(answer):
    return [t for t in BANNED_IDENTIFIERS if t.lower() in answer.lower()]


def renamed_categories(answer):
    """Category-shaped labels that are not one of the three real names."""
    low = answer.lower()
    hits = [r for r in CATEGORY_RENAMES if r in low]
    # Drop overlapping variants so "world foods" isn't also reported as
    # "world food" - one mistake should be one finding.
    hits = [h for h in hits if not any(h != o and h in o for o in hits)]
    if hits and not any(c in low for c in CATEGORIES):
        return hits
    return [h for h in hits if re.search(rf"categor\w*[^.]{{0,60}}{re.escape(h)}|{re.escape(h)}[^.]{{0,30}}categor\w*", low)]


def check_answer(answer, context, extra_allowed=()):
    """All checks at once -> list of {kind, detail}. Empty means clean."""
    issues = []
    for fig in ungrounded_figures(answer, context, extra_allowed):
        issues.append({"kind": "ungrounded_figure", "detail": fig["raw"]})
    for miss in misattributed_figures(answer, context):
        issues.append({"kind": "misattributed_figure",
                       "detail": f"{miss['raw']} attached to {miss['brand']}"})
    for tok in leaked_identifiers(answer):
        issues.append({"kind": "internal_identifier", "detail": tok})
    for name in renamed_categories(answer):
        issues.append({"kind": "renamed_category", "detail": name})
    return issues
