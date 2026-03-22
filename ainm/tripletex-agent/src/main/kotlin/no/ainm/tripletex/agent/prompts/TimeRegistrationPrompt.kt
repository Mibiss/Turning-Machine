package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object TimeRegistrationPrompt {
    private val TIME_RECIPE = """
TIME REGISTRATION + PROJECT INVOICE:
1. Find employee: GET /employee?email=EMAIL&fields=id,firstName,lastName
2. Find project: GET /project?fields=id,name,number
3. Find activity: GET /activity?name=ACTIVITY_NAME&fields=id,name
   - If not found, try: GET /activity?fields=id,name&count=100 to list all activities
4. Register hours: POST /timesheet/entry
   {"employee":{"id":EMP_ID},"project":{"id":PROJ_ID},"activity":{"id":ACT_ID},"date":"YYYY-MM-DD","hours":HOURS,"chargeableHours":HOURS,"chargeable":true}
   - For multiple days, create one entry per day or use POST /timesheet/entry/list with array
5. Create project invoice:
   a. Create order: POST /order {"customer":{"id":CID},"project":{"id":PROJ_ID},"orderDate":"DATE","deliveryDate":"DATE"}
   b. Add order line: POST /order/orderline {"order":{"id":OID},"description":"Activity name","count":HOURS,"unitPriceExcludingVatCurrency":RATE,"vatType":{"id":3}}
   c. Invoice the order: PUT /order/OID/:invoice?invoiceDate=DATE
      Use tripletex_put with path="/order/OID/:invoice?invoiceDate=DATE" and body="{}"
IMPORTANT: Do NOT use /timeEntry or /projectActivity - those don't exist! Use /timesheet/entry and /activity.

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a TIME REGISTRATION task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(TIME_RECIPE)
        appendLine()
        appendLine(CommonPrompts.VAT_TYPES_OUTGOING)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
