# One function per extraction target. Each builds the user-message text
# (labelled so the model knows which section is which) and calls the LLM
# under the matching schema + system prompt. No filing I/O or parser
# logic here - that's the pipeline's job; these take already-sliced text.

from app.extraction import models, prompts
from app.extraction.llm import LLMClient


def extract_risk_factor_changes(
    llm: LLMClient, current_item_1a: str, prior_item_1a: str | None
) -> models.RiskFactorChanges:
    if prior_item_1a:
        text = (
            "=== CURRENT YEAR - ITEM 1A ===\n"
            f"{current_item_1a}\n\n"
            "=== PRIOR YEAR - ITEM 1A ===\n"
            f"{prior_item_1a}"
        )
    else:
        text = (
            "=== CURRENT YEAR - ITEM 1A (no prior year available) ===\n"
            f"{current_item_1a}"
        )
    return llm.extract(
        system=prompts.RISK_FACTOR_CHANGES,
        text=text,
        schema=models.RiskFactorChanges,
    )


def extract_management_tone(llm: LLMClient, item_7: str) -> models.ManagementTone:
    return llm.extract(
        system=prompts.MANAGEMENT_TONE,
        text=f"=== ITEM 7 - MD&A ===\n{item_7}",
        schema=models.ManagementTone,
    )


def extract_going_concern(
    llm: LLMClient, text: str
) -> models.GoingConcernOpinion:
    return llm.extract(
        system=prompts.GOING_CONCERN,
        text=text,
        schema=models.GoingConcernOpinion,
    )


def extract_related_party(
    llm: LLMClient, anchored_text: str
) -> models.RelatedPartyTransactions:
    return llm.extract(
        system=prompts.RELATED_PARTY,
        text=f"=== RELATED-PARTY DISCLOSURE (from Item 8 notes) ===\n{anchored_text}",
        schema=models.RelatedPartyTransactions,
    )


def extract_revenue_concentration(
    llm: LLMClient, text: str
) -> models.RevenueConcentration:
    return llm.extract(
        system=prompts.REVENUE_CONCENTRATION,
        text=text,
        schema=models.RevenueConcentration,
    )
