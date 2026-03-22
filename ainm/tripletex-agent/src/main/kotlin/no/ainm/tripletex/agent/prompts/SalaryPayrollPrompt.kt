package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object SalaryPayrollPrompt {
    private val SALARY_RECIPE = """
SALARY / PAYROLL:

STEP 1 - Find employee:
GET /employee?email=EMAIL&fields=id,firstName,lastName,email,dateOfBirth

STEP 2 - Employee prerequisites (includes division check!):
IMPORTANT: Before creating a new division, ALWAYS check if one exists first!
  GET /division?fields=id,name&count=1 — if a division exists, USE IT. Only create a new one if NONE exist.
${CommonPrompts.EMPLOYEE_PREREQUISITE_CHECK}

STEP 3 - Configure salary settings (REQUIRED for tax calculation):
GET /salary/settings?fields=*
If municipality is null or missing:
  GET /municipality?fields=id,name&count=1
  PUT /salary/settings with {"id":SETTINGS_ID,"version":VER,"municipality":{"id":MUN_ID}}
This is CRITICAL — without municipality, tax deductions cannot be computed!

STEP 4 - Set employment details (REQUIRED for salary processing):
After creating/verifying employment, set employment details:
POST /employee/employment/details {"employment":{"id":EMPL_ID},"date":"2026-01-01","percentageOfFullTimeEquivalent":100.0,"annualSalary":ANNUAL_SALARY}
- annualSalary = monthly salary × 12 (e.g. if base salary is 42350, annual = 508200)
- Use 100.0 for full-time unless prompt specifies otherwise

STEP 5 - Find salary types:
GET /salary/type?fields=id,name&count=200
CRITICAL: Search through the FULL returned list for exact name matches. Do NOT guess or assume IDs!
- "Fastlønn" = fixed monthly salary
- "Timelønn" = hourly wage
- BONUS TYPE SELECTION:
  Search the list for BOTH "Bonus/tantieme" AND "Bonus"
  If "Bonus/tantieme" exists, prefer it (standard Norwegian bonus type)
  If only "Bonus" exists, use that
  Do NOT create your own salary type — use what's in the list!
- "Engangsutbetaling" = one-time payment
- If prompt says "bonificación"/"bonus"/"Bonus", use whichever bonus type exists in the list
- NEVER use an ID unless you found it in the actual API response!

STEP 6 - Create salary transaction:
POST /salary/transaction?generateTaxDeduction=true
{"year":YEAR,"month":MONTH,"date":"YYYY-MM-DD","payslips":[
  {"employee":{"id":EMP_ID},"date":"YYYY-MM-DD","year":YEAR,"month":MONTH,"specifications":[
    {"salaryType":{"id":FASTLONN_ID},"rate":AMOUNT,"count":1,"description":"Fastlønn"},
    {"salaryType":{"id":BONUS_ID},"rate":BONUS_AMT,"count":1,"description":"Bonus"}
  ]}
]}
CRITICAL STRUCTURE: employee goes on PAYSLIP level, NOT on transaction level!
- "rate" = amount per unit, "count" = number of units (use count=1 for fixed amounts)
- Use the last day of the month for date (e.g. "2026-03-31" for March)
- Do NOT fall back to manual vouchers - the competition expects real salary transactions

STEP 7 - STOP. Do not verify or re-fetch.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a SALARY/PAYROLL task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(SALARY_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
