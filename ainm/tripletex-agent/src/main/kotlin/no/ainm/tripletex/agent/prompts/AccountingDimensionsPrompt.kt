package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object AccountingDimensionsPrompt {
    private val DIMENSIONS_RECIPE = """
ACCOUNTING DIMENSIONS (custom/free dimensions):
1. GET /ledger/accountingDimensionName?fields=* to see existing dimensions
2. POST /ledger/accountingDimensionName {"dimensionName":"Koststed"} to create
   - Field is "dimensionName" (NOT "name"!)
   - Response includes "dimensionIndex" — SAVE THIS VALUE!
3. GET /ledger/accountingDimensionValue?dimensionNameId=DIM_ID&fields=* to see existing values
4. POST /ledger/accountingDimensionValue?dimensionNameId=DIM_ID with body {"displayName":"Oslo","number":"001"}
   - Field is "displayName" (NOT "name"!)
   - dimensionNameId goes as QUERY PARAMETER, not in the body
5. On voucher postings, map dimensionIndex to the correct field:
   - dimensionIndex=0 → "freeAccountingDimension1":{"id":VALUE_ID}
   - dimensionIndex=1 → "freeAccountingDimension2":{"id":VALUE_ID}
   - CRITICAL: Check the dimensionIndex from step 2! Do NOT always use freeAccountingDimension1!
   - Example: if dimensionIndex=1, use "freeAccountingDimension2":{"id":VALUE_ID}

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing an ACCOUNTING DIMENSIONS task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(DIMENSIONS_RECIPE)
        appendLine()
        appendLine(CommonPrompts.COMMON_ACCOUNTS)
        appendLine()
        appendLine(CommonPrompts.VOUCHER_POSTING_RULES)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
