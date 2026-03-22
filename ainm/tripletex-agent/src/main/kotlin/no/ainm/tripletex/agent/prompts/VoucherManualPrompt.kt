package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object VoucherManualPrompt {
    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a MANUAL JOURNAL ENTRY (VOUCHER) task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(CommonPrompts.VOUCHER_POSTING_RULES)
        appendLine()
        appendLine(CommonPrompts.COMMON_ACCOUNTS)
        appendLine()
        appendLine("FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.")
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
