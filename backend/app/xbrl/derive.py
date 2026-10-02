# Ratios derived purely from already-extracted MetricSnapshots (no extra
# fetch). Values are plain fractions (0.469, not 46.9) - format as a
# percentage at display time, except cash_runway_months (unit "months").

from app.xbrl.models import MetricSnapshot


def derive_ratios(snapshots: list[MetricSnapshot]) -> list[MetricSnapshot]:
    """Compute ratio metrics from already-extracted snapshots. Skips a
    ratio if a required input is missing or its denominator is zero.
    Cash runway is only derived when operating cash flow is negative;
    debt-to-equity only when equity is positive."""
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

    total_assets = by_key.get("total_assets")
    if current_assets and current_liabilities and total_assets and total_assets.value:
        derived.append(
            _snapshot(
                "working_capital_to_assets",
                current_assets,
                (current_assets.value - current_liabilities.value) / total_assets.value,
                "(current_assets-current_liabilities)/total_assets",
            )
        )

    cash = by_key.get("cash_and_equivalents")
    operating_cash_flow = by_key.get("operating_cash_flow")
    if cash and operating_cash_flow and operating_cash_flow.value < 0:
        monthly_burn = -operating_cash_flow.value / 12
        derived.append(
            _snapshot(
                "cash_runway_months",
                cash,
                cash.value / monthly_burn,
                "cash_and_equivalents/(-operating_cash_flow/12)",
                unit="months",
            )
        )

    long_term_debt = by_key.get("long_term_debt")
    short_term_debt = by_key.get("short_term_debt")
    equity = by_key.get("stockholders_equity")
    if long_term_debt and equity and equity.value > 0:
        total_debt = long_term_debt.value + (
            short_term_debt.value if short_term_debt else 0.0
        )
        derived.append(
            _snapshot(
                "debt_to_equity",
                long_term_debt,
                total_debt / equity.value,
                "(long_term_debt+short_term_debt)/stockholders_equity",
            )
        )

    total_liabilities = by_key.get("total_liabilities")
    if total_liabilities and total_assets and total_assets.value:
        derived.append(
            _ratio_snapshot("liabilities_to_assets", total_liabilities, total_assets)
        )

    operating_income = by_key.get("operating_income")
    interest_expense = by_key.get("interest_expense")
    if operating_income and interest_expense and interest_expense.value > 0:
        derived.append(
            _ratio_snapshot("interest_coverage", operating_income, interest_expense)
        )

    return derived


def _snapshot(
    metric_key: str,
    base: MetricSnapshot,
    value: float,
    xbrl_tag: str,
    unit: str = "ratio",
) -> MetricSnapshot:
    return MetricSnapshot(
        ticker=base.ticker,
        cik=base.cik,
        fiscal_year=base.fiscal_year,
        metric_key=metric_key,
        value=value,
        unit=unit,
        xbrl_tag=xbrl_tag,
        source="derived",
        filed_at=base.filed_at,
    )


def _ratio_snapshot(
    metric_key: str, numerator: MetricSnapshot, denominator: MetricSnapshot
) -> MetricSnapshot:
    return _snapshot(
        metric_key,
        numerator,
        numerator.value / denominator.value,
        f"{numerator.metric_key}/{denominator.metric_key}",
    )
