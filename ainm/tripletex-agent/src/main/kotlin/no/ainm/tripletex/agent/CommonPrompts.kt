package no.ainm.tripletex.agent

/**
 * Shared prompt fragments used across multiple task-specific prompts.
 * Extracted from the original monolithic system prompt to avoid duplication.
 */
object CommonPrompts {

    val HEADER = """
LANGUAGE: Prompts may be in Norwegian (nb/nn), English, Spanish, Portuguese, German, or French. Parse them all.

SCORING: You are scored on CORRECTNESS (right fields) and EFFICIENCY (fewer API calls, fewer errors). Every 4xx error REDUCES your score. Plan carefully before calling.

TOOLS: You have tripletex_get/post/put/delete for API calls, and tripletex_docs for looking up API documentation.
Use tripletex_docs when you encounter an unfamiliar endpoint or need to know exact field names. But prefer the RECIPES below first - they contain battle-tested patterns.
""".trimIndent()

    val CRITICAL_RULES = """
CRITICAL RULES:
1. Parse the prompt FULLY before making ANY API call. Plan your sequence of calls first.
2. The account may have pre-existing data. SEARCH before creating (e.g. GET /customer to find existing).
3. After a successful POST, extract the "id" from response["value"]["id"] and use it directly.
4. NEVER use placeholder IDs. Wait for real IDs from responses.
5. Create prerequisites ONE AT A TIME in order. Wait for each response.
6. If a call fails with 422, read the validationMessages, fix it, and retry ONCE correctly.
7. Minimize API calls. Don't fetch what you already know. NEVER list all accounts — always look up by number.
8. NEVER give up. If one approach fails, try an alternative. Always complete the task. If you get 403 errors, they may be transient — retry the same call after a pause. Do NOT stop the task due to 403 errors.
9. NEVER brute-force. If an approach fails 2 times, switch to a different strategy. Do NOT retry the same failing pattern with minor variations.
10. Do NOT modify employee data (bankAccount, name) that was not requested in the prompt. Exception: dateOfBirth MUST be set if null when creating employment for salary processing.
11. When the prompt specifies account numbers (e.g. "debit 1500, credit 3400"), look up their IDs directly — do NOT browse or search for alternatives.
12. STOP as soon as all required actions are done. Do NOT verify by re-fetching, do NOT summarize, do NOT check trial balances. HTTP 201 confirms success. Every extra API call wastes time and may cause rate limiting.
13. URL query parameters: the FIRST parameter uses ?, subsequent ones use &. Correct: /path/123?fields=id&count=10 Wrong: /path/123&fields=id
14. NEVER ask questions or request more information. You are an autonomous agent — proceed with whatever information is given. If something is missing, use reasonable defaults or skip optional steps.
""".trimIndent()

    val API_BASE = """
TRIPLETEX API (base URL already includes /v2):

Response format: List={"fullResultSize":N,"values":[...]} Single={"value":{"id":123,...}}
Search: ?fields=id,name&count=100 or ?name=Acme&fields=*
Account lookup: GET /ledger/account?number=1920 (exact match by account number)
""".trimIndent()

    val FOOTER = """
DATES: "YYYY-MM-DD". Today's date is provided in the user message.
AMOUNTS: Use numbers not strings. E.g. 19500 not "19500".
ORGANIZATION NUMBERS: Always use string type, e.g. "organizationNumber":"123456789"
""".trimIndent()

    val COMMON_ACCOUNTS = """
Common accounts: 1500=Kundefordringer, 1920=Bankinnskudd, 2400=Leverandørgjeld, 2710=Inngående MVA, 3000=Salgsinntekt, 4000=Innkjøp, 6300=Leie lokale, 8060=Valutagevinst (agio), 8160=Valutatap (disagio)
Look up by: GET /ledger/account?number=NNNN&fields=id,number,name
Create missing account: POST /ledger/account {"number":NNNN,"name":"Account Name"} — do NOT include "type" field, Tripletex assigns it automatically based on the number range!
""".trimIndent()

    val FIND_OR_CREATE_CUSTOMER = """
Find/create customer: GET /customer?organizationNumber=ORG&fields=id,name or POST /customer → CID
POST /customer {"name":"Acme AS","organizationNumber":"123456789","email":"x@y.no","isCustomer":true}
Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}
Phone: "phoneNumber":"12345678" or "phoneNumberMobile":"12345678"
""".trimIndent()

    val CREATE_ORDER_AND_ORDERLINES = """
Order creation:
1. POST /order {"customer":{"id":CID},"orderDate":"DATE","deliveryDate":"DATE"} → OID
   - If this is a PROJECT invoice, ALSO include "project":{"id":PROJ_ID} to link the order to the project!
2. For EACH product line:
   a. Search product: GET /product?number=PROD_NUM&fields=id,number,name
   b. If not found, create: POST /product {"name":"Product Name","number":PROD_NUM,"priceExcludingVatCurrency":PRICE,"vatType":{"id":VAT_ID}}
      - Product number MUST be a positive integer (e.g. 1001), NOT a string!
   c. POST /order/orderline {"order":{"id":OID},"product":{"id":PROD_ID},"description":"Product Name","count":QTY,"unitPriceExcludingVatCurrency":PRICE,"vatType":{"id":VAT_ID}}
   - If the prompt includes numbers in parentheses like "Item (1234)", then 1234 is the PRODUCT NUMBER
   - ALWAYS include "vatType" on order lines
   - ALWAYS include "product":{"id":PROD_ID} when you have a product
""".trimIndent()

    val VAT_TYPES_OUTGOING = """
VAT TYPES for outgoing invoices:
- id=3: 25% MVA (standard rate, "høy sats")
- id=31: 15% MVA (food/beverage, "middels sats", "Lebensmittel"/"matvarer")
- id=33: 12% MVA (transport/cinema, "lav sats")
- id=6: 0% exempt (outside VAT law, "avgiftsfri"/"befreit"/"exempt")
- id=5: 0% within VAT law (no outgoing VAT but still in VAT system)
- "ohne MwSt."/"ekskl. MVA"/"excl. VAT"/"sem IVA"/"sin IVA"/"hors TVA"/"uten MVA" means the AMOUNT is excluding VAT, but 25% VAT still applies! Use vatType id=3 (25%).
- ONLY use vatType id=6 (0%) if the prompt explicitly says "avgiftsfri"/"tax exempt"/"fritatt"/"exento de IVA"/"isento de IVA"/"exonéré de TVA"/"steuerfrei"
""".trimIndent()

    val VOUCHER_POSTING_RULES = """
VOUCHER POSTING RULES:
IMPORTANT: Before creating a voucher, ALWAYS look up account IDs first!
  GET /ledger/account?number=1500&fields=id,number,name → use the "id" from response (e.g. 472677033), NOT the account number!
POST /ledger/voucher {"date":"DATE","description":"Description","postings":[
  {"row":1,"date":"DATE","account":{"id":ACCT_ID_FROM_LOOKUP},"amount":AMOUNT,"amountGross":AMOUNT,"amountGrossCurrency":AMOUNT},
  {"row":2,"date":"DATE","account":{"id":ACCT_ID_FROM_LOOKUP},"amount":-AMOUNT,"amountGross":-AMOUNT,"amountGrossCurrency":-AMOUNT}
]}
- account.id MUST be the Tripletex internal ID from GET /ledger/account lookup, NOT the account number!
- Positive amount = debit, negative = credit
- amountGross MUST equal amountGrossCurrency
- Each posting needs row (1,2,...), date, account, amount, amountGross, amountGrossCurrency
- For customer-linked accounts (1500 Kundefordringer): add "customer":{"id":CID} on that posting
- For supplier-linked accounts (2400 Leverandørgjeld): add "supplier":{"id":SID} on that posting
- NEVER put "supplier" or "customer" on the voucher root object — they go INSIDE each posting!
- For VAT: add "vatType":{"id":N} on the EXPENSE posting only. Do NOT also post manually to 2710/2700 - Tripletex handles the VAT account automatically when vatType is set!
- For department: add "department":{"id":DEPT_ID} on each posting
- For VAT with vatType: set amount=NET, amountGross=GROSS, amountGrossCurrency=GROSS
""".trimIndent()

    val EMPLOYEE_PREREQUISITE_CHECK = """
EMPLOYEE PREREQUISITE CHECK:
1. Find employee: GET /employee?email=EMAIL&fields=id,firstName,lastName,email,dateOfBirth
2. If dateOfBirth is null AND the prompt provides a date of birth, set it. If dateOfBirth is null and NOT in the prompt, derive from nationalIdentityNumber (first 6 digits = DDMMYY): PUT /employee/EMP_ID {"id":EMP_ID,"dateOfBirth":"YYYY-MM-DD"}
3. Check employment: GET /employee/EMP_ID?fields=id,employments
4. If no employment OR division is null:
   a. Get division: GET /division?fields=id,name&count=1
   b. If NO divisions exist, create one:
      - GET /municipality?fields=id,name&count=1 → MUN_ID
      - GET /company?fields=organizationNumber to find the real org number
      - POST /division {"name":"Hovedkontor","organizationNumber":"REAL_ORG_NR","startDate":"2020-01-01","municipalityDate":"2020-01-01","municipality":{"id":MUN_ID}}
   c. If no employment: POST /employee/employment {"employee":{"id":EMP_ID},"startDate":"2026-01-01","division":{"id":DIV_ID},"isMainEmployer":true}
   d. If employment exists but division:null: PUT /employee/employment/EMPL_ID {"id":EMPL_ID,"version":VER,"division":{"id":DIV_ID}}
""".trimIndent()

    val BANK_ACCOUNT_SETUP = """
BANK ACCOUNT (required for invoicing):
- If invoice creation fails with "selskapet har registrert et bankkontonummer", the company needs a bank account.
- Bank accounts are stored as LEDGER ACCOUNTS with isBankAccount=true, NOT on /company or /bank!
- Step 1: GET /ledger/account?number=1920&fields=* to check if account 1920 exists
- Step 2a: If it exists but has no bankAccountNumber, update it:
  PUT /ledger/account/ID {"id":ID,"version":VER,"number":1920,"name":"Bankkonto","isBankAccount":true,"bankAccountNumber":"86011117947"}
- Step 2b: If account 1920 doesn't exist, create it:
  POST /ledger/account {"number":1920,"name":"Bankkonto","isBankAccount":true,"bankAccountNumber":"86011117947"}
- Use a valid Norwegian bank account number (11 digits, MOD11): "86011117947"
""".trimIndent()

    val ENDPOINTS_REFERENCE = """
Endpoints:
- /employee - GET, POST, PUT
- /customer - GET, POST, PUT (customers)
- /supplier - GET, POST, PUT (suppliers - separate from customers!)
- /product - GET, POST
- /order - GET, POST, PUT
- /order/orderline - GET, POST, PUT (NOT /orderline!)
- /invoice - GET, POST (requires invoiceDateFrom/To for GET)
- /invoice/paymentType - GET (get available payment type IDs)
- /travelExpense - GET, POST, PUT, DELETE
- /travelExpense/cost - GET, POST (expense line items)
- /travelExpense/mileageAllowance - GET, POST (km allowance)
- /travelExpense/perDiemCompensation - GET, POST (daily allowance)
- /travelExpense/accommodationAllowance - GET, POST (accommodation)
- /activity - GET (list/search activities)
- /timesheet/entry - GET, POST, PUT, DELETE (time registration)
- /project - GET, POST
- /project/orderline - GET, POST (project order lines)
- /department - GET, POST
- /division - GET, POST (business entities/virksomheter for employment)
- /municipality - GET (lookup municipality IDs for division creation)
- /employee/employment/details - GET, POST (employment details: position %, salary)
- /employee/standardTime - GET, POST (standard working hours per day)
- /salary/type - GET (salary types: Fastlønn, Bonus, etc.)
- /salary/transaction - POST (create salary run with nested payslips)
- /salary/settings - GET, PUT (salary settings including municipality)
- /ledger/account - GET (chart of accounts, filter: ?number=1920)
- /ledger/vatType - GET (VAT types)
- /ledger/voucher - GET, POST, DELETE (requires dateFrom/To for GET)
- /ledger/voucher/{id}/:reverse - PUT (reverse a voucher, creates counter-entry)
- /ledger/posting - GET
- /ledger/paymentTypeOut - GET (outgoing payment types)
- /ledger/accountingDimensionName - GET, POST (custom dimension names)
- /ledger/accountingDimensionValue - GET, POST (custom dimension values)
- /supplierInvoice - GET, POST (incoming invoices from suppliers)
- /currency - GET
""".trimIndent()
}
