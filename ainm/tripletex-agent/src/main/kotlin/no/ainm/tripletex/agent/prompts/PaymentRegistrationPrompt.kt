package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object PaymentRegistrationPrompt {
    private val PAYMENT_RECIPE = """
REGISTER PAYMENT ON INVOICE:
This is a PUT with QUERY PARAMETERS (not a POST with body!):
1. GET /invoice/paymentType?fields=id,description to find payment type IDs
2. PUT /invoice/INVOICE_ID/:payment?paymentDate=YYYY-MM-DD&paymentTypeId=PT_ID&paidAmount=AMOUNT&paidAmountCurrency=AMOUNT
   - paymentTypeId: get from step 1 (e.g. "Betalt til bank" for bank payment)
   - paidAmount: the amount paid (for partial payment, use the partial amount)
   - paidAmountCurrency: same as paidAmount for NOK invoices
   - Use tripletex_put with path="/invoice/ID/:payment?paymentDate=...&paymentTypeId=...&paidAmount=...&paidAmountCurrency=..." and body="{}"

To find the invoice first:
- GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2026-12-31&fields=id,invoiceNumber,amount,amountOutstanding
- Or search by customer: GET /invoice?customerId=CID&invoiceDateFrom=...&invoiceDateTo=...

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 200 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a PAYMENT REGISTRATION task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(PAYMENT_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
