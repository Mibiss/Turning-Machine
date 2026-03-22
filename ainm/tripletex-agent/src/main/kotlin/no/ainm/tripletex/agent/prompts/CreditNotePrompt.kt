package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object CreditNotePrompt {
    private val CREDIT_NOTE_RECIPE = """
CREDIT NOTE (for existing invoice):
Use the dedicated credit note endpoint - DO NOT create negative order lines:
1. Find the original invoice: GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2026-12-31&fields=id,invoiceNumber,customer,amount
2. PUT /invoice/INVOICE_ID/:createCreditNote?date=YYYY-MM-DD&comment=Reason
   - Use tripletex_put with path="/invoice/ID/:createCreditNote?date=DATE&comment=REASON" and body="{}"
   - This automatically creates the credit note linked to the original invoice
3. STOP. Do not verify or re-fetch.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a CREDIT NOTE task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(CREDIT_NOTE_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
