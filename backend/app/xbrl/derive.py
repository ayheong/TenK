# Ratios derived purely from already-extracted MetricSnapshots (no extra
# fetch). Values are plain fractions (0.469, not 46.9) — format as a
# percentage at display time.

from app.xbrl.models import MetricSnapshot


def derive_ratios(snapshots: list[MetricSnapshot]) -> list[MetricSnapshot]:
    """Compute ratio metrics from already-extracted snapshots. Skips a
    ratio if a required input is missing or its denominator is zero."""
    by_key = {s.metric_key: s for s in snapshots}
    revenue = by_key.get("revenue")
    derived = []

    gross_profit = by_key.get("gross_profit")
    if gross_profit and revenue and revenue.value:
        derived.append(_ratio_snapshot("gross_margin", gross_profit, revenue))

    rd_expense = by_key.get("rd_expense")
    if rd_expense and revenue and revenue.value:
        derived.append(_ratio_snapshot("rd_pct_revenue", rd_expense, revenue))

    current_assets = by_key.get("current_assets")
    current_liabilities = by_key.get("current_liabilities")
    if current_assets and current_liabilities and current_liabilities.value:
        derived.append(
            _ratio_snapshot(
                "working_capital_ratio", current_assets, current_liabilities
            )
        )

    return derived


def _ratio_snapshot(
    metric_key: str, numerator: MetricSnapshot, denominator: MetricSnapshot
) -> MetricSnapshot:
    return MetricSnapshot(
        ticker=numerator.ticker,
        cik=numerator.cik,
        fiscal_year=numerator.fiscal_year,
        metric_key=metric_key,
        value=numerator.value / denominator.value,
        unit="ratio",
        xbrl_tag=f"{numerator.metric_key}/{denominator.metric_key}",
        source="derived",
        filed_at=numerator.filed_at,
    )
