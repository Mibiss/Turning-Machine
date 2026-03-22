package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object TravelExpensePrompt {
    private val TRAVEL_RECIPE = """
TRAVEL EXPENSE (reiseregning):
1. Find employee: GET /employee?email=EMAIL&fields=id,firstName,lastName,email (or search by name)

2. Get payment type AND cost categories (do BOTH in parallel):
   - GET /travelExpense/paymentType?fields=id,description (use "Privat utlegg" for employee-paid expenses)
   - GET /travelExpense/costCategory?fields=id,description (needed for step 4 — pick the category matching each cost type)

3. POST /travelExpense with travelDetails to create a TRAVEL REPORT (not employee expense):
{"employee":{"id":EMP_ID},"title":"Trip title","travelDetails":{"departureDate":"DATE","returnDate":"DATE","destination":"City","purpose":"Full purpose from prompt"}}
CRITICAL: Include "travelDetails" with departureDate/returnDate/destination - without it, it creates an "ansattutlegg" (employee expense) instead of "reiseregning" (travel report), and per diem will fail!
DATE CALCULATION: If prompt gives exact dates, use them. If it only says "X days", the trip already happened — use today as returnDate and calculate departureDate = today - (X-1) days.

4. Add costs (flights, taxi, etc.):
POST /travelExpense/cost {"travelExpense":{"id":TE_ID},"costCategory":{"id":CC_ID},"date":"DATE","comments":"Flight","amountCurrencyIncVat":2500,"paymentType":{"id":PT_ID}}
- costCategory is REQUIRED! Pick the best matching category from step 2 (e.g. "Fly" for flights, "Taxi" for taxi, "Transport" for generic transport)
- Field is "amountCurrencyIncVat" (NOT "amount"!)
- Field is "comments" (NOT "description"!)
- paymentType must be an object {"id":PT_ID}

5. Add per diem (diett/dagpenger):
POST /travelExpense/perDiemCompensation {"travelExpense":{"id":TE_ID},"count":DAYS,"rate":RATE,"location":"City","overnightAccommodation":"HOTEL"}
- "location" is REQUIRED - use the destination city
- "overnightAccommodation": "HOTEL" for multi-day trips, "NONE" for day trips
- "rate": Use the rate from the prompt (e.g. "dagssats 800 kr" → rate:800)
- "count": Use number of DAYS from the prompt (NOT nights!). E.g. "5 days" → count:5, "3 dager" → count:3

6. Add mileage allowance (kjøregodtgjørelse) — only if driving/mileage is mentioned:
POST /travelExpense/mileageAllowance {"travelExpense":{"id":TE_ID},"date":"DATE","departureLocation":"From","destination":"To","km":150}

7. Add accommodation (ALWAYS add for multi-day trips):
POST /travelExpense/accommodationAllowance {"travelExpense":{"id":TE_ID},"count":NIGHTS,"location":"City"}
- count = number of NIGHTS = DAYS minus 1. E.g. "4 days" → count:3, "5 days" → count:4, "2 days" → count:1
- This is DIFFERENT from per diem count! Per diem = DAYS, accommodation = NIGHTS = DAYS - 1
- IMPORTANT: Always add accommodation allowance for trips longer than 1 day, even if not explicitly mentioned in the prompt.

STEP 8 - STOP. Do not verify or re-fetch.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a TRAVEL EXPENSE task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(TRAVEL_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
