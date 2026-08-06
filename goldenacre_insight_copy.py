"""The Insights page's narrative copy, in one place.

Deliberately a ROOT-LEVEL module, not part of goldenacre_analytics_engine.

Two consumers must never disagree: goldenacre_insights_app.py renders these as
cards, and multi-agents/scripts/build_goldenacre_audio.py pre-generates the
spoken clips from the very same strings. Duplicating the wording in the audio
builder would reintroduce this project's most persistent failure mode - hand-
written narrative drifting away from the live figures beside it - except the
drift would be audible and invisible to a code review of the page.

It lives here rather than in the engine because a Streamlit Cloud container was
observed running a NEW goldenacre_insights_app.py against an OLD
multi-agents/scripts/goldenacre_analytics_engine.py, which is not a state any
single commit produces - every commit has been checked and each is internally
consistent. Whatever causes that mixed checkout, copy that the entry script
imports from the repo root is not reachable by it: a genuinely stale container
fails with a plain ModuleNotFoundError for this file instead of an AttributeError
on a half-updated module, which says what is actually wrong.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "multi-agents" / "scripts"))
from goldenacre_analytics_engine import pct_change  # noqa: E402


def build_insight_texts(kpis, manufacturer_view):
    """The Insights page's narrative cards, as [(key, html), ...].

    Lives here, not in the Streamlit app, because it has two consumers that must
    never disagree: the app renders these as cards, and
    build_goldenacre_audio.py pre-generates the spoken clips from the very same
    strings. Duplicating the wording in the audio builder would reintroduce this
    project's most persistent failure mode - hand-written narrative drifting away
    from the live figures beside it - except this time the drift would be audible
    and invisible to a code review of the page.
    """
    price_mat = kpis["avg_price_per_unit_mat"]
    price_mat_ya = kpis["value_sales_mat_ya"] / kpis["unit_sales_mat_ya"] if kpis["unit_sales_mat_ya"] else None
    price_change = pct_change(price_mat, price_mat_ya) if price_mat_ya else None

    # The price clause is built conditionally on BOTH facts it asserts. The
    # previous version hardcoded the "cushioned" conclusion regardless of which
    # way price actually moved, so a refresh in which price fell would have had
    # the card claim the exact opposite of its own figures; and when price_change
    # was None it emitted a dangling fragment starting with " - ".
    value_dir = "down" if kpis["value_sales_change_pct"] < 0 else "up"
    unit_dir = "fell" if kpis["unit_sales_change_pct"] < 0 else "rose"
    if price_change is None:
        price_clause = "."
    else:
        # All four quadrants, because the wording is not symmetric: price/mix
        # either reinforces the volume move or works against it, and "cushioned"
        # only makes sense against a decline. Getting this from the data rather
        # than hardcoding it is the point - the previous copy asserted
        # "cushioned...decline" unconditionally.
        volume_fell = kpis["unit_sales_change_pct"] < 0
        same_direction = (price_change > 0) == (not volume_fell)
        if volume_fell:
            effect = "compounded the volume decline" if same_direction else "cushioned part of the volume decline"
        else:
            effect = "added to the volume gain" if same_direction else "offset part of the volume gain"
        price_clause = (
            f", while average price per unit {'rose' if price_change > 0 else 'fell'} "
            f"{abs(price_change):.1f}% - price/mix {effect}."
        )

    cards = [
        ("insight_1",
         f"<strong>Overall value sales are {value_dir} {abs(kpis['value_sales_change_pct']):.1f}% MAT vs. MAT YA</strong> "
         f"(£{kpis['value_sales_mat']/1e9:.2f}bn vs. £{kpis['value_sales_mat_ya']/1e9:.2f}bn). Unit sales "
         f"{unit_dir} {abs(kpis['unit_sales_change_pct']):.1f}%" + price_clause),
        ("insight_2",
         f"<strong>{kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value sales</strong> "
         f"(£{kpis['unmatched_value_sales_mat']/1e9:.2f}bn) sit in products with no product-reference match at all - "
         "the single biggest lever for sharper category reporting is expanding reference-database coverage, not merchandising."),
    ]

    ga_share = manufacturer_view["golden_acre_share"]
    ga_corr = manufacturer_view["najma_rank_correction"]
    cards.append((
        "insight_ga",
        f"<strong>Golden Acre is gaining share in a shrinking category.</strong> Halal overall is down "
        f"{abs(manufacturer_view['category_total']['value_yoy_pct']):.1f}% MAT, but Najma + Jaldee Eats' combined "
        f"share rose {'+' if ga_share['share_point_change'] > 0 else ''}{ga_share['share_point_change']:.2f}pp - and "
        f"gained share in every retailer it's listed in, not just on average. Najma's true rank is #{ga_corr['corrected_rank']} "
        f"(not #{ga_corr['naive_rank']} - see Golden Acre View for why), and the clearest near-term lever isn't demand, "
        f"it's distribution: Jaldee Eats is Tesco-only while Najma is already established in the other three retailers."
    ))

    extras = manufacturer_view.get("portfolio_extras") or {}
    rows = (extras.get("owned_extra") or []) + (extras.get("distributed") or [])
    if rows:
        by_brand = ", ".join(
            f"{r['brand'].title()} £{r['value_sales_mat']/1e3:.0f}k ({r['value_yoy_pct']:+.0f}%)" for r in rows
        )
        # Client-facing copy: states what the numbers are and what they mean,
        # not how the analysis arrived at them. The provenance (found via
        # AC_MANUFACTURER, absent from the "Our Brands" page) belongs in the
        # method notes, not in a card the client reads and hears.
        owned_names = [r["brand"].title() for r in extras.get("owned_extra") or []]
        cards.append((
            "insight_extras",
            f"<strong>Golden Acre's fastest growth is outside the Halal category.</strong> "
            f"{by_brand}. {' and '.join(owned_names) or 'These'} "
            f"{'is an own brand' if len(owned_names) == 1 else 'are own brands'}; X Energy is one Golden Acre "
            f"distributes rather than owns, so it sits outside own-brand share. Neither falls into Halal, Polish "
            f"or Other, so neither appears in any category breakdown - see Golden Acre View for the detail."
        ))
    return cards
