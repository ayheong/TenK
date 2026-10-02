# Canonical metric key -> candidate (taxonomy, XBRL tag) pairs, in fallback
# order. The first tag present in a company's Company Facts data wins.
#
# Revenue and shares-outstanding tags vary most across filers: older filers
# use `Revenues` (pre-ASC 606), newer ones `RevenueFromContractWith...`;
# `EntityCommonStockSharesOutstanding` (dei, cover page) is a fallback for
# companies missing the balance-sheet `CommonStockSharesOutstanding` tag.
METRIC_TAGS: dict[str, list[tuple[str, str]]] = {
    "revenue": [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss"),
    ],
    "operating_cash_flow": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ],
    "long_term_debt": [
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebt"),
    ],
    "short_term_debt": [
        ("us-gaap", "LongTermDebtCurrent"),
        ("us-gaap", "ShortTermBorrowings"),
        ("us-gaap", "DebtCurrent"),
    ],
    "gross_profit": [
        ("us-gaap", "GrossProfit"),
    ],
    "current_assets": [
        ("us-gaap", "AssetsCurrent"),
    ],
    "current_liabilities": [
        ("us-gaap", "LiabilitiesCurrent"),
    ],
    "shares_outstanding": [
        ("us-gaap", "CommonStockSharesOutstanding"),
        ("dei", "EntityCommonStockSharesOutstanding"),
    ],
    "rd_expense": [
        ("us-gaap", "ResearchAndDevelopmentExpense"),
    ],
    "cash_and_equivalents": [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        (
            "us-gaap",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
    ],
    "total_assets": [
        ("us-gaap", "Assets"),
    ],
    "total_liabilities": [
        ("us-gaap", "Liabilities"),
    ],
    "stockholders_equity": [
        ("us-gaap", "StockholdersEquity"),
        (
            "us-gaap",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
    ],
    "operating_income": [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
    "interest_expense": [
        ("us-gaap", "InterestExpense"),
        ("us-gaap", "InterestExpenseDebt"),
    ],
}
