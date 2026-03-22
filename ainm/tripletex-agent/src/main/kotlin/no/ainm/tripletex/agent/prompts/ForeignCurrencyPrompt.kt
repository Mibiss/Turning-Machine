package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object ForeignCurrencyPrompt {
    private val FOREIGN_CURRENCY_RECIPE = """
FOREIGN CURRENCY PAYMENT WITH EXCHANGE DIFFERENCE (disagio/agio):

STEP 1 - Find customer and invoice:
- GET /customer?organizationNumber=ORG&fields=id,name
- GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2026-12-31&customerId=CID&fields=id,invoiceNumber,amount,amountOutstanding,currency
- Note the amountOutstanding from the API response

STEP 2 - Register payment to CLOSE the invoice:
- GET /invoice/paymentType?fields=id,description (find "Betalt til bank" or "Kontant")
- PUT /invoice/INV_ID/:payment?paymentDate=TODAY&paymentTypeId=PT_ID&paidAmount=AMOUNT_OUTSTANDING&paidAmountCurrency=AMOUNT_OUTSTANDING
- CRITICAL: Use paidAmount = amountOutstanding from the invoice! This CLOSES the invoice to zero.
- Do NOT multiply by exchange rates! The paidAmount must equal amountOutstanding to close the invoice.

STEP 3 - Calculate the exchange difference:
- Use the EUR amount from the PROMPT (e.g. "11497 EUR")
- Use the 'calculate' tool: operation="exchange_diff", params={"amount": EUR_AMOUNT, "invoice_rate": ORIGINAL_RATE, "payment_rate": NEW_RATE}
- If payment rate > invoice rate → GAIN (agio/valutagevinst) → account 8060
- If payment rate < invoice rate → LOSS (disagio/valutatap) → account 8160
- The exchange difference amount = EUR_AMOUNT × |payment_rate - invoice_rate|

STEP 4 - Book the exchange difference as a voucher:
- Look up accounts: GET /ledger/account?number=8060&fields=id (for gain) or GET /ledger/account?number=8160&fields=id (for loss)
  If account doesn't exist, CREATE it: POST /ledger/account {"number":8160,"name":"Valutatap"}
  Also: GET /ledger/account?number=1500&fields=id (Kundefordringer)
- POST /ledger/voucher:
  For GAIN (agio, payment rate > invoice rate):
    Debit 1500 (Kundefordringer): +DIFF_AMOUNT (increase receivable)
    Credit 8060 (Valutagevinst): -DIFF_AMOUNT (income)
  For LOSS (disagio, payment rate < invoice rate):
    Debit 8160 (Valutatap): +DIFF_AMOUNT (expense)
    Credit 1500 (Kundefordringer): -DIFF_AMOUNT (reduce receivable)
  MUST include "customer":{"id":CID} on BOTH posting lines!

STEP 5 - STOP. Do not verify.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a FOREIGN CURRENCY PAYMENT task.")
        appendLine("You have a 'calculate' tool for exact arithmetic — ALWAYS use it for exchange difference calculations.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(FOREIGN_CURRENCY_RECIPE)
        appendLine()
        appendLine(CommonPrompts.COMMON_ACCOUNTS)
        appendLine()
        appendLine(CommonPrompts.VOUCHER_POSTING_RULES)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
