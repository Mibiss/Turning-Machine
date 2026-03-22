package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object LedgerAnalysisPrompt {
    private val ANALYSIS_RECIPE = """
LEDGER ANALYSIS (finding trends, biggest changes between periods):
When asked to analyze ledger data (e.g. "find expense accounts with biggest increase"):
1. First get an employee for later use: GET /employee?fields=id,firstName,lastName&count=1
2. GET ALL postings for BOTH periods in a SINGLE call — the system auto-computes monthly summaries:
   GET /ledger/posting?dateFrom=2026-01-01&dateTo=2026-02-28&fields=account,amount,date&count=1000
   The response includes a [POSTING SUMMARY] with per-account monthly totals and changes — use those EXACT values!
3. From the summary, find expense accounts (4000-7999) with the largest ABSOLUTE increase (change value).
   IMPORTANT: Only accounts 4000-7999 are operating expenses. Accounts 8000-8999 are financial items (agio/disagio) — do NOT include them!
   Do NOT re-calculate — use the pre-computed "change:" values from the summary.
4. Pick the top N accounts as requested.
5. Create projects/activities using the employee from step 1 as projectManager:
   a. POST /project {"name":"Account Name","projectManager":{"id":EMP_ID},"startDate":"2026-01-01","isInternal":true}
   b. POST /activity {"name":"Account Name","activityType":"PROJECT_GENERAL_ACTIVITY"}
   c. LINK activity to project: POST /project/projectActivity {"project":{"id":PROJ_ID},"activity":{"id":ACT_ID}}
      This linking step is REQUIRED — creating the activity alone does NOT associate it with the project!
CRITICAL: Use a SINGLE call with count=1000 spanning both months. The system provides pre-computed summaries.

FINAL STEP - STOP. Do not verify or re-fetch.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a LEDGER ANALYSIS task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(ANALYSIS_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
