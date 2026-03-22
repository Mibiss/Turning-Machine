package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object CustomerCreatePrompt {
    private val CUSTOMER_RECIPE = """
CUSTOMER: POST /customer
{"name":"Acme AS","organizationNumber":"123456789","email":"x@y.no","isCustomer":true}
- Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}
- Phone: "phoneNumber":"12345678" or "phoneNumberMobile":"12345678"
- SEARCH before creating: GET /customer?organizationNumber=ORG&fields=id,name
- Include ALL fields from the prompt: organizationNumber, email, phoneNumber, postalAddress, etc.

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a CUSTOMER CREATION task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(CUSTOMER_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
