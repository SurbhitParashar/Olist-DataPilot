from __future__ import annotations

import re


UNSUPPORTED_TERMS = {
    "stock price": "stock prices",
    "stock prices": "stock prices",
    "share price": "share prices",
    "share prices": "share prices",
    "weather": "weather",
    "gender": "customer gender",
    "income": "customer income",
    "demographics": "customer demographics",
    "population": "population",
    "bitcoin": "bitcoin",
    "crypto": "cryptocurrency",
    "salary": "employee salary",
    "employee": "employee information",
    "inventory on hand": "inventory levels",
    "age": "customer age",
}


def guard_query(query: str) -> str | None:
    """
    Perform a lightweight pre-agent guardrail.

    This function should only reject questions that clearly require
    data outside the Olist dataset.

    It must NOT decide whether a query is analytically valid.
    The LLM agent is responsible for interpreting valid Olist questions.
    """

    q = query.lower().strip()

    if not q:
        return "Please enter an analytics question."

    for term, description in UNSUPPORTED_TERMS.items():
        # Match complete words/phrases instead of arbitrary substrings.
        #
        # This prevents:
        #   "age" from matching "average"
        #
        # while still matching:
        #   "customer age"
        #   "age of customers"
        pattern = rf"(?<!\w){re.escape(term)}(?!\w)"

        if re.search(pattern, q):
            return (
                f"The dataset does not contain {description} as an "
                "analytics dimension. No chart was generated."
            )

    return None