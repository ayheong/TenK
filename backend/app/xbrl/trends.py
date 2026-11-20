# Multi-year trend metrics, built from the same Company Facts payload already
# fetched for the current year - no extra requests. Company Facts holds every
# year a company has reported, so a trend is just a different read of it.
#
# Rules that keep trends honest:
#   - only rows from 10-Ks filed on or before the analyzed filing, so an older
#     filing never "sees" the future;
#   - flow metrics (revenue, income) must cover a full year, which drops the
#     quarterly rows some 10-Ks also carry;
#   - when a period was restated, the most recently filed value wins;
#   - a comparison year is the fiscal year ending ~N years before the current
#     one (within a tolerance), not "N rows back", so gaps never silently
#     shift the window.

from datetime import date, timedelta

from app.edgar.models import FilingRecord
from app.xbrl.models import MetricSnapshot
from app.xbrl.tags import METRIC_TAGS

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}
MIN_ANNUAL_DAYS = 350
MAX_ANNUAL_DAYS = 380
WINDOW_YEARS = 3
MATCH_TOLERANCE_DAYS = 45
STALE_SHARES_DAYS = 120

Series = list[tuple[date, float]]


def _duration_days(entry: dict) -> int | None:
    if "start" not in entry:
        return None
    return (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days


def annual_series(
    facts: dict,
    metric_key: str,
    filing: FilingRecord,
    candidates: list[tuple[str, str]] | None = None,
    anchor: date | None = None,
    tolerance_days: int = MATCH_TOLERANCE_DAYS,
) -> tuple[Series, str | None]:
    """Annual values for a metric, oldest first, plus the XBRL tag used.

    Uses the first candidate tag that has any usable annual row, so a company
    that switched tags (older `Revenues`, newer contract-revenue tag) still
    yields one consistent series from its most current tag. When `anchor` is
    given, a tag is only used if it reports a value for that year, so a tag a
    company has stopped using never supplies the "current" end of a trend.
    """
    for taxonomy, tag in candidates or METRIC_TAGS.get(metric_key, []):
        tag_data = facts.get(taxonomy, {}).get(tag)
        if not tag_data:
            continue
        by_end: dict[date, tuple[str, float]] = {}
        for entries in tag_data["units"].values():
            for entry in entries:
                if entry.get("form") not in ANNUAL_FORMS:
                    continue
                if entry.get("filed", "") > filing.filing_date.isoformat():
                    continue
                days = _duration_days(entry)
                if days is not None and not MIN_ANNUAL_DAYS <= days <= MAX_ANNUAL_DAYS:
                    continue
                end = date.fromisoformat(entry["end"])
                current = by_end.get(end)
                if current is None or entry["filed"] > current[0]:
                    by_end[end] = (entry["filed"], entry["val"])
        if by_end:
            series = sorted((end, val) for end, (_, val) in by_end.items())
            if anchor is not None and not _near(series, anchor, tolerance_days):
                continue
            return series, tag
    return [], None


def _near(series: Series, anchor: date, tolerance_days: int) -> bool:
    return any(abs((end - anchor).days) <= tolerance_days for end, _ in series)


def _latest_up_to(series: Series, fiscal_year_end: date | None) -> tuple[date, float] | None:
    """The newest point at or before the analyzed fiscal year end. Without a
    known year end, the newest point overall."""
    eligible = [p for p in series if fiscal_year_end is None or p[0] <= fiscal_year_end]
    return eligible[-1] if eligible else None


def _point_years_before(
    series: Series, anchor: date, years: int
) -> tuple[date, float] | None:
    """The point nearest to `years` before `anchor`, within a tolerance."""
    target = anchor - timedelta(days=round(365.25 * years))
    best = min(series, key=lambda p: abs((p[0] - target).days), default=None)
    if best is None or abs((best[0] - target).days) > MATCH_TOLERANCE_DAYS:
        return None
    return best


def _snapshot(
    filing: FilingRecord,
    base: MetricSnapshot,
    key: str,
    value: float,
    unit: str,
    tag: str,
) -> MetricSnapshot:
    return MetricSnapshot(
        ticker=base.ticker,
        cik=base.cik,
        fiscal_year=base.fiscal_year,
        metric_key=key,
        value=value,
        unit=unit,
        xbrl_tag=tag,
        source="derived",
        filed_at=base.filed_at,
    )


def _looks_like_split(window: Series) -> bool:
    """Company Facts reports share counts as originally filed, not adjusted
    for later splits, so a single-year jump this large is a split rather than
    dilution or buybacks. Comparing across it would be meaningless."""
    return any(
        prev and not 0.55 <= val / prev <= 1.8
        for (_, prev), (_, val) in zip(window, window[1:])
    )


def _growth(current: float, past: float) -> float | None:
    """Relative change, measured against the size of the earlier value so a
    move out of a loss reads as an improvement. Undefined from zero."""
    if past == 0:
        return None
    return (current - past) / abs(past)


def derive_trends(
    facts: dict, filing: FilingRecord, current: list[MetricSnapshot]
) -> list[MetricSnapshot]:
    """Trend metrics for the analyzed filing. Each is skipped when its history
    is missing, so a recent IPO or a sparse filer simply has fewer trends."""
    by_key = {s.metric_key: s for s in current}
    anchor_metric = by_key.get("revenue") or by_key.get("net_income") or next(
        iter(current), None
    )
    if anchor_metric is None:
        return []
    out: list[MetricSnapshot] = []
    fye = filing.fiscal_year_end

    revenue, revenue_tag = annual_series(facts, "revenue", filing, anchor=fye)
    latest_rev = _latest_up_to(revenue, fye)
    if latest_rev:
        prior = _point_years_before(revenue, latest_rev[0], 1)
        if prior and (g := _growth(latest_rev[1], prior[1])) is not None:
            out.append(
                _snapshot(filing, anchor_metric, "revenue_yoy_pct", g, "ratio",
                          f"{revenue_tag} (yoy)")
            )
        past = _point_years_before(revenue, latest_rev[0], WINDOW_YEARS)
        if past and past[1] > 0 and latest_rev[1] > 0:
            cagr = (latest_rev[1] / past[1]) ** (1 / WINDOW_YEARS) - 1
            out.append(
                _snapshot(filing, anchor_metric, "revenue_cagr_3y", cagr, "ratio",
                          f"{revenue_tag} (3y CAGR)")
            )

    gross, gross_tag = annual_series(facts, "gross_profit", filing, anchor=fye)
    latest_gp = _latest_up_to(gross, fye)
    if latest_rev and latest_gp and latest_rev[0] == latest_gp[0] and latest_rev[1]:
        past_rev = _point_years_before(revenue, latest_rev[0], WINDOW_YEARS)
        past_gp = _point_years_before(gross, latest_gp[0], WINDOW_YEARS)
        if past_rev and past_gp and past_rev[1] and past_rev[0] == past_gp[0]:
            change = latest_gp[1] / latest_rev[1] - past_gp[1] / past_rev[1]
            out.append(
                _snapshot(filing, anchor_metric, "gross_margin_change_3y", change,
                          "ratio", f"{gross_tag}/{revenue_tag} (3y change)")
            )

    # Balance-sheet counts are dated at year end and cover-page counts a few
    # weeks before filing, so anchor on the filing date with a wide tolerance.
    shares, shares_tag = annual_series(
        facts, "shares_outstanding", filing,
        anchor=filing.filing_date, tolerance_days=STALE_SHARES_DAYS,
    )
    latest_sh = _latest_up_to(shares, None)
    if latest_sh:
        past = _point_years_before(shares, latest_sh[0], WINDOW_YEARS)
        window = [p for p in shares if past and past[0] <= p[0] <= latest_sh[0]]
        if (
            past
            and not _looks_like_split(window)
            and (g := _growth(latest_sh[1], past[1])) is not None
        ):
            out.append(
                _snapshot(filing, anchor_metric, "share_count_change_3y_pct", g,
                          "ratio", f"{shares_tag} (3y change)")
            )

    debt, debt_tag = annual_series(facts, "long_term_debt", filing, anchor=fye)
    latest_debt = _latest_up_to(debt, fye)
    if latest_debt:
        past = _point_years_before(debt, latest_debt[0], WINDOW_YEARS)
        if past and (g := _growth(latest_debt[1], past[1])) is not None:
            out.append(
                _snapshot(filing, anchor_metric, "long_term_debt_change_3y_pct", g,
                          "ratio", f"{debt_tag} (3y change)")
            )

    income, income_tag = annual_series(facts, "net_income", filing, anchor=fye)
    recent = [p for p in income if fye is None or p[0] <= fye][-WINDOW_YEARS:]
    consecutive = all(
        (b[0] - a[0]).days <= MAX_ANNUAL_DAYS + MATCH_TOLERANCE_DAYS
        for a, b in zip(recent, recent[1:])
    )
    if len(recent) == WINDOW_YEARS and consecutive:
        out.append(
            _snapshot(filing, anchor_metric, "net_loss_years_3y",
                      float(sum(1 for _, v in recent if v < 0)), "count",
                      f"{income_tag} (last 3 years)")
        )

    return out


HISTORY_YEARS = 5
# Metric keys charted in the demo, with the series each needs.
HISTORY_METRICS = ["revenue", "net_income", "long_term_debt", "shares_outstanding"]


def metric_history(
    facts: dict, filing: FilingRecord, years: int = HISTORY_YEARS
) -> dict[str, dict]:
    """Recent annual values for the metrics behind the trends, oldest first, so
    a reader can see the shape and not just the summary number. Each entry has
    the unit, the XBRL tag and `points` of (period end, value). Share counts
    are as originally filed, so a split shows as a jump. Metrics with fewer
    than two points are left out: one point is not a trend."""
    fye = filing.fiscal_year_end
    out: dict[str, dict] = {}
    for key in HISTORY_METRICS:
        if key == "shares_outstanding":
            series, tag = annual_series(
                facts, key, filing,
                anchor=filing.filing_date, tolerance_days=STALE_SHARES_DAYS,
            )
            unit = "shares"
        else:
            series, tag = annual_series(facts, key, filing, anchor=fye)
            unit = "USD"
        if fye is not None and key != "shares_outstanding":
            series = [p for p in series if p[0] <= fye]
        series = series[-years:]
        if len(series) >= 2:
            out[key] = {"unit": unit, "xbrl_tag": tag, "points": series}

    revenue, _ = annual_series(facts, "revenue", filing, anchor=fye)
    gross, gross_tag = annual_series(facts, "gross_profit", filing, anchor=fye)
    revenue_by_end = dict(revenue)
    margins = [
        (end, value / revenue_by_end[end])
        for end, value in gross
        if revenue_by_end.get(end) and (fye is None or end <= fye)
    ][-years:]
    if len(margins) >= 2:
        out["gross_margin"] = {
            "unit": "ratio", "xbrl_tag": f"{gross_tag}/revenue", "points": margins,
        }
    return out
