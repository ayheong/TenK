from app.edgar.client import Client
from app.edgar.models import FilingRecord
from app.xbrl.derive import derive_ratios
from app.xbrl.models import MetricSnapshot
from app.xbrl.tags import METRIC_TAGS


def company_facts_url(cik: int) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def fetch_company_facts(client: Client, cik: int) -> dict:
    """Fetch a company's XBRL Company Facts payload."""
    data = client.get_json(company_facts_url(cik))
    return data.get("facts", {})


def _match_fact(
    entries: list[dict], accession: str, fiscal_year_end: str | None
) -> dict | None:
    """Pick the fact for this filing's fiscal year, falling back to any
    fact from the same accession (e.g. dei cover-page tags report an
    `end` date near the filing date rather than the fiscal year end)."""
    accession_matches = [e for e in entries if e.get("accn") == accession]
    if fiscal_year_end is not None:
        for entry in accession_matches:
            if entry.get("end") == fiscal_year_end:
                return entry
    return accession_matches[0] if accession_matches else None


def _find_fact(
    facts: dict,
    candidates: list[tuple[str, str]],
    accession: str,
    fiscal_year_end: str | None,
) -> tuple[str, str, dict] | None:
    for taxonomy, tag in candidates:
        tag_data = facts.get(taxonomy, {}).get(tag)
        if not tag_data:
            continue
        for unit, entries in tag_data["units"].items():
            match = _match_fact(entries, accession, fiscal_year_end)
            if match is not None:
                return tag, unit, match
    return None


def _prior_period_value(
    facts: dict,
    candidates: list[tuple[str, str]],
    accession: str,
    fiscal_year_end: str,
) -> float | None:
    """Find the comparative prior-year figure for a metric, reported
    alongside the current year in the same 10-K (income statements show
    2-3 years of history in one filing) — no extra fetch required."""
    for taxonomy, tag in candidates:
        tag_data = facts.get(taxonomy, {}).get(tag)
        if not tag_data:
            continue
        for entries in tag_data["units"].values():
            prior_entries = sorted(
                (
                    e
                    for e in entries
                    if e.get("accn") == accession and e.get("end") != fiscal_year_end
                ),
                key=lambda e: e["end"],
                reverse=True,
            )
            if prior_entries:
                return prior_entries[0]["val"]
    return None


def extract_metrics_from_facts(
    facts: dict, filing: FilingRecord
) -> list[MetricSnapshot]:
    """Extract canonical MetricSnapshots for one filing from an
    already-fetched Company Facts payload.

    Metrics with no matching tag in any fallback are silently skipped —
    not every filer reports every canonical metric (e.g. no inventory
    for a services company).
    """
    fiscal_year_end = (
        filing.fiscal_year_end.isoformat() if filing.fiscal_year_end else None
    )

    snapshots = []
    for metric_key, candidates in METRIC_TAGS.items():
        found = _find_fact(facts, candidates, filing.accession, fiscal_year_end)
        if found is None:
            continue
        tag, unit, match = found
        snapshots.append(
            MetricSnapshot(
                ticker=filing.ticker,
                cik=filing.cik,
                fiscal_year=match["fy"],
                metric_key=metric_key,
                value=match["val"],
                unit=unit,
                xbrl_tag=tag,
                source="company_facts",
                filed_at=match["filed"],
            )
        )
    return snapshots


def extract_metrics(client: Client, filing: FilingRecord) -> list[MetricSnapshot]:
    """Fetch Company Facts and extract canonical MetricSnapshots for one
    filing. See `extract_metrics_from_facts` for the skip-on-missing rule.
    """
    facts = fetch_company_facts(client, filing.cik)
    return extract_metrics_from_facts(facts, filing)


def extract_net_income_yoy_from_facts(
    facts: dict, filing: FilingRecord, current: list[MetricSnapshot]
) -> MetricSnapshot | None:
    """Year-over-year net income change, using the comparative prior-year
    figure already present in the filing's own Company Facts data. Returns
    None if net_income wasn't extracted, there's no prior-year figure in
    the same accession, or the prior figure is zero (YoY % undefined)."""
    net_income = next((s for s in current if s.metric_key == "net_income"), None)
    if net_income is None or filing.fiscal_year_end is None:
        return None

    prior_value = _prior_period_value(
        facts,
        METRIC_TAGS["net_income"],
        filing.accession,
        filing.fiscal_year_end.isoformat(),
    )
    if not prior_value:
        return None

    return MetricSnapshot(
        ticker=net_income.ticker,
        cik=net_income.cik,
        fiscal_year=net_income.fiscal_year,
        metric_key="net_income_yoy_pct",
        value=(net_income.value - prior_value) / prior_value,
        unit="ratio",
        xbrl_tag=f"{net_income.xbrl_tag} (yoy)",
        source="derived",
        filed_at=net_income.filed_at,
    )


def extract_all(client: Client, filing: FilingRecord) -> list[MetricSnapshot]:
    """Fetch Company Facts once and return canonical metrics plus every
    derivable ratio (gross margin, R&D % of revenue, net income YoY %)."""
    facts = fetch_company_facts(client, filing.cik)
    snapshots = extract_metrics_from_facts(facts, filing)
    snapshots += derive_ratios(snapshots)

    yoy = extract_net_income_yoy_from_facts(facts, filing, snapshots)
    if yoy is not None:
        snapshots.append(yoy)

    return snapshots
