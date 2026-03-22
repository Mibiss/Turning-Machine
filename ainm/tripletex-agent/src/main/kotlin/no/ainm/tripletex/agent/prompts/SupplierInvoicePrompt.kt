package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object SupplierInvoicePrompt {
    private val SUPPLIER_INVOICE_RECIPE = """
SUPPLIER INVOICE (incoming):
1. Search supplier first: GET /supplier?organizationNumber=ORG_NR&fields=id,name,organizationNumber
2. If not found: POST /supplier {"name":"X","organizationNumber":"123"} → SID
3. Look up expense account: GET /ledger/account?number=NNNN&fields=id,number,name
4. Look up supplier debt account: GET /ledger/account?number=2400&fields=id,number,name
5. Create supplier invoice WITH embedded voucher:
   POST /supplierInvoice {"invoiceNumber":"INV-001","supplier":{"id":SID},"invoiceDate":"DATE","invoiceDueDate":"DUE_DATE","amount":GROSS,"amountCurrency":GROSS,"amountExcludingVat":NET,"amountExcludingVatCurrency":NET,
   "voucher":{"date":"DATE","description":"Description","postings":[
     {"row":1,"date":"DATE","account":{"id":EXPENSE_ACCT},"amount":NET,"amountGross":GROSS,"amountGrossCurrency":GROSS,"supplier":{"id":SID},"vatType":{"id":VAT_ID}},
     {"row":2,"date":"DATE","account":{"id":2400_ACCT},"amount":-GROSS,"amountGross":-GROSS,"amountGrossCurrency":-GROSS,"supplier":{"id":SID}}
   ]}}
   CRITICAL: Include ALL four amount fields on the supplierInvoice: "amount":GROSS, "amountCurrency":GROSS, "amountExcludingVat":NET, "amountExcludingVatCurrency":NET. Without them, the invoice amount shows as 0.
   CRITICAL: Do NOT create a separate manual voucher! The embedded voucher already creates the accounting entries. A second voucher would DOUBLE the postings!
CRITICAL: Each posting MUST include "supplier":{"id":SID}!
- invoiceDueDate should be 30 days after invoiceDate
- VAT TYPE SELECTION for incoming invoices:
  * 25% MVA (standard): vatType id=1, amount=net (gross/1.25), amountGross=gross
  * 15% MVA (food): vatType id=11, amount=net (gross/1.15), amountGross=gross
  * 0% / exempt / no VAT mentioned: omit vatType entirely, amount=amountGross=same value
  * If unsure, GET /ledger/vatType?fields=id,name&count=50 to find the correct incoming VAT type
  * IMPORTANT: Do NOT default to id=1 if the invoice says "uten MVA"/"ekskl. mva"/"VAT exempt" — omit vatType!

SUPPLIER: POST /supplier
{"name":"Supplier AS","organizationNumber":"123456789","email":"e@x.no","phoneNumber":"12345678"}
- Note: Use /supplier endpoint, NOT /customer with isSupplier!
- Include ALL fields from the prompt: organizationNumber, email, phoneNumber, postalAddress, etc.
- Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}

FINAL STEP - STOP. Do not verify or re-fetch. HTTP 201 confirms success.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a SUPPLIER INVOICE task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(SUPPLIER_INVOICE_RECIPE)
        appendLine()
        appendLine(CommonPrompts.COMMON_ACCOUNTS)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
