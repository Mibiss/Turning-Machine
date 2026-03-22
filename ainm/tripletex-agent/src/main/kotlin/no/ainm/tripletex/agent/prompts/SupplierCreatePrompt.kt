package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object SupplierCreatePrompt {
    private val SUPPLIER_RECIPE = """
SUPPLIER: POST /supplier
{"name":"Supplier AS","organizationNumber":"123456789","email":"e@x.no","phoneNumber":"12345678"}
- Note: Use /supplier endpoint, NOT /customer with isSupplier!
- Include ALL fields from the prompt: organizationNumber, email, phoneNumber, postalAddress, etc.
- Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}
- SEARCH before creating: GET /supplier?organizationNumber=ORG&fields=id,name

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a SUPPLIER CREATION task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(SUPPLIER_RECIPE)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
