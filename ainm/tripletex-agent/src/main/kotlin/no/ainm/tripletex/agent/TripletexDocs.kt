package no.ainm.tripletex.agent

object TripletexDocs {

    fun search(query: String): String {
        val q = query.lowercase()
        val matches = docs.filter { (keywords, _) ->
            keywords.any { q.contains(it) || it.contains(q) }
        }.map { it.second }

        return if (matches.isEmpty()) {
            "No documentation found for '$query'. Try searching for an endpoint path like '/employee/employment' or a topic like 'salary', 'invoice', 'voucher'."
        } else {
            matches.joinToString("\n\n---\n\n")
        }
    }

    // Each entry: Pair(listOf(keywords), documentation)
    private val docs: List<Pair<List<String>, String>> = listOf(

        listOf("employee", "/employee") to """
ENDPOINT: /employee
Methods: GET, POST, PUT
GET params: ?email=x@y.no&fields=id,firstName,lastName,email,dateOfBirth
POST body: {"firstName":"X","lastName":"Y","dateOfBirth":"1986-05-20","email":"x@y.no","allowInformationRegistration":true,"userType":"STANDARD","department":{"id":DEPT_ID}}
Key fields: id, firstName, lastName, dateOfBirth (YYYY-MM-DD), email, phoneNumberMobile, department (object {"id":N}), employeeNumber, nationalIdentityNumber, allowInformationRegistration, userType ("STANDARD")
PUT: Include id and version from GET response. Only send fields you want to change.
""".trim(),

        listOf("employment", "/employee/employment") to """
ENDPOINT: /employee/employment
Methods: GET, POST, PUT
POST body: {"employee":{"id":EMP_ID},"startDate":"2026-04-12","division":{"id":DIV_ID},"isMainEmployer":true}
Key fields: id, version, employee (object), startDate, endDate, division (object - REQUIRED for salary!), isMainEmployer, taxDeductionCode, employmentId
NOTE: Endpoint is /employee/employment (NOT /employee/{id}/employment!)
NOTE: Do NOT include "employmentType" - it doesn't exist and causes 422.
NOTE: division is REQUIRED. If no divisions exist, create one via POST /division.
PUT: /employee/employment/ID with id, version, and fields to update.
""".trim(),

        listOf("employment/details", "stillingsprosent", "position", "annual salary", "årslønn", "percentage") to """
ENDPOINT: /employee/employment/details
Methods: GET, POST
POST body: {"employment":{"id":EMPL_ID},"date":"2026-04-12","percentageOfFullTimeEquivalent":80.0,"annualSalary":840000}
Key fields: employment (object {"id":N}), date (start date), percentageOfFullTimeEquivalent (0-100, e.g. 80.0 for 80%), annualSalary (yearly salary in NOK)
GET params: ?employmentId=EMPL_ID&fields=*
Use this to set position percentage and annual salary after creating employment.
""".trim(),

        listOf("standardtime", "standard time", "working hours", "arbeidstid", "hours per day") to """
ENDPOINT: /employee/standardTime
Methods: GET, POST
POST body: {"employee":{"id":EMP_ID},"fromDate":"2026-04-12","hoursPerDay":6.0}
Key fields: employee (object {"id":N}), fromDate (effective from date - NOT "date"!), hoursPerDay (decimal, e.g. 7.5 for standard full-time, 6.0 for 80%)
Use this to configure standard daily working hours for an employee.
IMPORTANT: The field is "fromDate", NOT "date"!
""".trim(),

        listOf("division", "/division", "virksomhet") to """
ENDPOINT: /division
Methods: GET, POST
POST body: {"name":"Hovedkontor","organizationNumber":"ORG_NR","startDate":"2020-01-01","municipalityDate":"2020-01-01","municipality":{"id":MUN_ID}}
Key fields: id, name, organizationNumber, startDate, municipalityDate, municipality (object {"id":N} - REQUIRED, get from GET /municipality)
Required for employee employment. If none exist, create one before creating employment.
NOTE: Use the company's REAL organizationNumber (GET /company?fields=organizationNumber), not a placeholder!
""".trim(),

        listOf("municipality", "/municipality", "kommune") to """
ENDPOINT: /municipality
Methods: GET (read-only)
GET params: ?fields=id,name&count=1
Returns list of Norwegian municipalities. Use the id when creating divisions.
""".trim(),

        listOf("department", "/department", "avdeling") to """
ENDPOINT: /department
Methods: GET, POST
POST body: {"name":"Utvikling","departmentNumber":"200"}
Key fields: id, name, departmentNumber, departmentManager (object), isInactive
GET params: ?name=X&fields=id,name,departmentNumber
""".trim(),

        listOf("customer", "/customer", "kunde") to """
ENDPOINT: /customer
Methods: GET, POST, PUT
POST body: {"name":"Acme AS","organizationNumber":"123456789","email":"x@y.no","isCustomer":true}
Key fields: id, name, organizationNumber, email, invoiceEmail, phoneNumber, phoneNumberMobile, isCustomer, isSupplier, isInactive
Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}
GET params: ?organizationNumber=123&fields=id,name or ?name=Acme&fields=*
""".trim(),

        listOf("supplier", "/supplier", "leverandør") to """
ENDPOINT: /supplier
Methods: GET, POST, PUT
POST body: {"name":"Supplier AS","organizationNumber":"123456789","email":"e@x.no","phoneNumber":"12345678"}
Key fields: id, name, organizationNumber, email, phoneNumber, postalAddress, isInactive
Address: "postalAddress":{"addressLine1":"Street 1","postalCode":"0000","city":"Oslo"}
NOTE: Use /supplier endpoint, NOT /customer with isSupplier!
""".trim(),

        listOf("order", "/order") to """
ENDPOINT: /order
Methods: GET, POST, PUT
POST body: {"customer":{"id":CID},"orderDate":"2026-03-21","deliveryDate":"2026-03-21"}
Key fields: id, customer (object), orderDate, deliveryDate, project (object, optional)
To invoice: PUT /order/OID/:invoice?invoiceDate=DATE with body="{}"
""".trim(),

        listOf("orderline", "order line", "/order/orderline") to """
ENDPOINT: /order/orderline
Methods: GET, POST, PUT
POST body: {"order":{"id":OID},"product":{"id":PROD_ID},"description":"Item","count":1,"unitPriceExcludingVatCurrency":1000,"vatType":{"id":3}}
Key fields: order (object), product (object, optional), description, count, unitPriceExcludingVatCurrency, vatType (object {"id":N})
vatType IDs: 3=25% outgoing, 31=15% food, 33=12% transport, 6=0% exempt, 5=0% within law
NOTE: Always include vatType!
""".trim(),

        listOf("invoice", "/invoice", "faktura") to """
ENDPOINT: /invoice
Methods: GET
GET params: ?invoiceDateFrom=2025-01-01&invoiceDateTo=2026-12-31&customerId=CID&fields=id,invoiceNumber,amount,amountOutstanding
Key fields: id, invoiceNumber, invoiceDate, customer, amount, amountOutstanding, isCredited

Create invoice: PUT /order/OID/:invoice?invoiceDate=DATE (preferred method)
Credit note: PUT /invoice/ID/:createCreditNote?date=DATE&comment=REASON with body="{}"
Register payment: PUT /invoice/ID/:payment?paymentDate=DATE&paymentTypeId=PT_ID&paidAmount=AMOUNT with body="{}"
Payment types: GET /invoice/paymentType?fields=id,description
""".trim(),

        listOf("supplierinvoice", "supplier invoice", "/supplierinvoice", "leverandørfaktura") to """
ENDPOINT: /supplierInvoice
Methods: GET, POST
POST body: {"invoiceNumber":"INV-001","supplier":{"id":SID},"invoiceDate":"DATE","invoiceDueDate":"DUE",
  "voucher":{"date":"DATE","description":"Desc","postings":[
    {"row":1,"date":"DATE","account":{"id":EXPENSE_ACCT},"amount":NET,"amountGross":GROSS,"amountGrossCurrency":GROSS,"supplier":{"id":SID},"vatType":{"id":1}},
    {"row":2,"date":"DATE","account":{"id":2400_ACCT},"amount":-GROSS,"amountGross":-GROSS,"amountGrossCurrency":-GROSS,"supplier":{"id":SID}}
  ]}}
CRITICAL: API returns 500 without embedded voucher postings!
The embedded voucher handles accounting entries automatically. Do NOT create a separate voucher.
VAT TYPES (incoming): id=1 = 25% inngående MVA (standard). For 0% / exempt: omit vatType entirely.
GET /ledger/vatType for the full list if you need other rates.
""".trim(),

        listOf("product", "/product", "produkt") to """
ENDPOINT: /product
Methods: GET, POST
POST body: {"name":"Product X","number":1234,"priceExcludingVatCurrency":100,"vatType":{"id":3}}
Key fields: id, name, number (product number), priceExcludingVatCurrency, vatType
GET params: ?number=1234&fields=id,number,name (search by product number)
""".trim(),

        listOf("salary", "/salary", "lønn", "payroll") to """
ENDPOINT: /salary/transaction
Methods: POST
POST: /salary/transaction?generateTaxDeduction=true
Body: {"year":2026,"month":3,"date":"2026-03-31","payslips":[
  {"employee":{"id":EMP_ID},"date":"2026-03-31","year":2026,"month":3,"specifications":[
    {"salaryType":{"id":TYPE_ID},"rate":AMOUNT,"count":1,"description":"Fastlønn"}
  ]}]}
CRITICAL: employee goes on PAYSLIP level, NOT transaction level!
Salary types: GET /salary/type?fields=id,name&count=200 (find Fastlønn, Bonus, Timelønn etc.)
Prerequisites: Employee needs dateOfBirth, employment with division linked.
""".trim(),

        listOf("voucher", "/ledger/voucher", "bilag", "journal") to """
ENDPOINT: /ledger/voucher
Methods: GET, POST, DELETE
POST body: {"date":"DATE","description":"Desc","postings":[
  {"row":1,"date":"DATE","account":{"id":DEBIT_ACCT},"amount":AMT,"amountGross":AMT,"amountGrossCurrency":AMT},
  {"row":2,"date":"DATE","account":{"id":CREDIT_ACCT},"amount":-AMT,"amountGross":-AMT,"amountGrossCurrency":-AMT}
]}
Each posting: row, date, account (object), amount, amountGross, amountGrossCurrency
Optional per posting: customer, supplier, vatType, department, project
Reverse: PUT /ledger/voucher/ID/:reverse?date=DATE with body="{}"
""".trim(),

        listOf("account", "/ledger/account", "konto") to """
ENDPOINT: /ledger/account
Methods: GET
GET params: ?number=1920&fields=id,number,name (exact match by account number)
Common accounts: 1500=Kundefordringer, 1920=Bankinnskudd, 2400=Leverandørgjeld, 3000=Salgsinntekt, 4000=Innkjøp, 6300=Leie lokale, 8060=Valutatap, 8070=Valutagevinst
For bank account setup: PUT /ledger/account/ID with isBankAccount=true, bankAccountNumber="86011117947"
""".trim(),

        listOf("travel", "travelexpense", "/travelexpense", "reise") to """
ENDPOINT: /travelExpense
Methods: GET, POST, PUT, DELETE
POST body: {"employee":{"id":EMP_ID},"title":"Trip title","travelDetails":{"departureDate":"DATE","returnDate":"DATE","destination":"City","purpose":"Purpose"}}
CRITICAL: Include "travelDetails" - without it creates "ansattutlegg" instead of "reiseregning"!

Sub-endpoints:
- /travelExpense/cost: {"travelExpense":{"id":TE_ID},"date":"DATE","comments":"Flight","amountCurrencyIncVat":2500,"paymentType":{"id":PT_ID}}
- /travelExpense/perDiemCompensation: {"travelExpense":{"id":TE_ID},"count":DAYS,"rate":800,"location":"City","overnightAccommodation":"HOTEL"}
- /travelExpense/accommodationAllowance: {"travelExpense":{"id":TE_ID},"count":DAYS,"location":"City"}
- /travelExpense/mileageAllowance: {"travelExpense":{"id":TE_ID},"date":"DATE","departureLocation":"From","destination":"To","km":150}
Payment types: GET /travelExpense/paymentType?fields=id,description
""".trim(),

        listOf("project", "/project", "prosjekt") to """
ENDPOINT: /project
Methods: GET, POST, PUT
POST body: {"name":"Project X","number":"1","projectManager":{"id":EMP_ID},"startDate":"DATE","isInternal":true}
Key fields: id, name, number, projectManager (object), startDate (REQUIRED), customer (optional), isInternal (true for internal projects)
Fixed price: PUT /project/ID with "fixedprice":AMOUNT,"isFixedPrice":true
NOTE: field is "fixedprice" (all lowercase), NOT "fixedPrice"!

Project order lines: POST /project/orderline {"project":{"id":PID},...}
""".trim(),

        listOf("activity", "/activity", "aktivitet") to """
ENDPOINT: /activity
Methods: GET, POST
POST body: {"name":"Activity Name","activityType":"PROJECT_GENERAL_ACTIVITY"}
Key fields: id, name, activityType (REQUIRED!), description, isChargeable, rate
activityType values: "PROJECT_GENERAL_ACTIVITY" (for project activities), "GENERAL_ACTIVITY" (for general/non-project)
GET params: ?fields=id,name,activityType&count=100
""".trim(),

        listOf("timesheet", "time registration", "/timesheet", "timer") to """
ENDPOINT: /timesheet/entry
Methods: GET, POST, PUT, DELETE
POST body: {"employee":{"id":EMP_ID},"project":{"id":PROJ_ID},"activity":{"id":ACT_ID},"date":"2026-03-21","hours":8,"chargeableHours":8,"chargeable":true}
Activities: GET /activity?fields=id,name&count=100
NOTE: Use /timesheet/entry and /activity (NOT /timeEntry or /projectActivity!)
""".trim(),

        listOf("vattype", "vat type", "mva", "moms") to """
VAT TYPES (outgoing invoices):
- id=3: 25% MVA (standard rate)
- id=31: 15% MVA (food/beverage)
- id=33: 12% MVA (transport/cinema)
- id=6: 0% exempt (outside VAT law)
- id=5: 0% within VAT law

VAT TYPES (incoming/supplier):
- id=1: 25% inngående MVA

"ekskl. MVA"/"excl. VAT"/"sem IVA"/"ohne MwSt." = amount excludes VAT but 25% still applies (use id=3)
Only use id=6 for explicitly tax-exempt items.
Endpoint: GET /ledger/vatType for full list.
""".trim(),

        listOf("currency", "exchange", "valuta", "disagio", "agio") to """
FOREIGN CURRENCY / EXCHANGE DIFFERENCES:
When a customer paid at a different exchange rate:
1. Register payment for ACTUAL amount received: PUT /invoice/ID/:payment?paidAmount=ACTUAL_NOK
2. Create voucher for exchange difference:
   - LOSS (disagio): Debit 8060 Valutatap, Credit 1500 Kundefordringer
   - GAIN (agio): Debit 1500 Kundefordringer, Credit 8070 Valutagevinst
   - Include "customer":{"id":CID} on BOTH postings!
Accounts: 8060=Valutatap, 8070=Valutagevinst, 1500=Kundefordringer
""".trim(),

        listOf("dimension", "accounting dimension", "koststed") to """
ENDPOINT: /ledger/accountingDimensionName and /ledger/accountingDimensionValue
Dimension names: POST /ledger/accountingDimensionName {"dimensionName":"Koststed"} (field is "dimensionName" not "name"!)
Dimension values: POST /ledger/accountingDimensionValue?dimensionNameId=DIM_ID {"displayName":"Oslo","number":"001"} (field is "displayName" not "name"!)
On voucher postings: use "freeAccountingDimension{dimensionIndex+1}":{"id":VALUE_ID} — e.g. dimensionIndex=0→freeAccountingDimension1, dimensionIndex=1→freeAccountingDimension2
""".trim(),

        listOf("posting", "postings", "/ledger/posting", "ledger posting") to """
ENDPOINT: /ledger/posting
Methods: GET (read-only)
GET params: ?dateFrom=2026-01-01&dateTo=2026-01-31&fields=id,date,description,account,amount,amountGross,voucher&count=1000
Key fields: id, date, description, account (object with id,number,name), amount, amountGross, voucher (object), customer, supplier, department
Use count=1000 to get all postings in one request. Filter by date range.
For analysis: use &fields=id,date,account,amount to minimize response size.
Accounts: number 4000-7999 are typically expense accounts.
""".trim(),

        listOf("bank", "bankkonto", "bank account") to """
BANK ACCOUNT:
Bank accounts are LEDGER ACCOUNTS with isBankAccount=true.
1. GET /ledger/account?number=1920&fields=*
2. PUT /ledger/account/ID {"id":ID,"version":VER,"number":1920,"name":"Bankkonto","isBankAccount":true,"bankAccountNumber":"86011117947"}
Use a valid Norwegian bank account number (11 digits, MOD11): "86011117947"
Do NOT try /company or /bank endpoints!
""".trim()
    )
}
