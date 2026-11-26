"""Money in: owner contributions, loans, refunds and other income, plus transfers between accounts.

A transfer is one record: it is received into one account and paid out of another. It appears in
both accounts' histories, but it is not money in for the business: it is left out of business-wide
Money In, sales, expenses and profit."""

INCOME_KINDS = ["Owner contribution", "Loan", "Refund received", "Other income"]
TRANSFER = "Transfer"
KINDS = INCOME_KINDS + [TRANSFER]
