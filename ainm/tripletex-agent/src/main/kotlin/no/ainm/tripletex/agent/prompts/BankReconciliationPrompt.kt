package no.ainm.tripletex.agent.prompts

import no.ainm.tripletex.agent.CommonPrompts

object BankReconciliationPrompt {
    private val BANK_RECONCILIATION_RECIPE = """
BANK RECONCILIATION (bankavstemming):
Match bank statement entries against open invoices in Tripletex, then register payments.

STEP 1: Get all open customer invoices (outgoing):
  GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2026-12-31&fields=id,invoiceNumber,invoiceDate,customer,amount,amountOutstanding,isCredited
  - amountOutstanding > 0 means unpaid/partially paid
  - Match bank statement amounts to invoice amounts or amountOutstanding

STEP 2: Get all supplier invoices (incoming):
  GET /supplierInvoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2026-12-31&fields=id,invoiceNumber,invoiceDate,supplier,amount,amountCurrency
  - Note: supplierInvoice does NOT have amountOutstanding or isCredited fields!
  - If result is empty, also try without date filter: GET /supplierInvoice?fields=id,invoiceNumber,invoiceDate,supplier,amount,amountCurrency
  - If still empty, check by supplier ID: GET /supplierInvoice?supplierId=ID&fields=id,invoiceNumber,invoiceDate,supplier,amount,amountCurrency

STEP 3: Get payment types:
  GET /invoice/paymentType?fields=id,description
  - Use "Betalt til bank" type for bank payments

STEP 4: Register payments for each matched invoice:
  CUSTOMER INVOICES (incoming bank payments):
  - PUT /invoice/INVOICE_ID/:payment?paymentDate=DATE&paymentTypeId=PT_ID&paidAmount=AMOUNT&paidAmountCurrency=AMOUNT with body="{}"
  - For PARTIAL payments: set paidAmount to the partial amount, NOT the full invoice amount
  - For FULL payments: set paidAmount to the invoice amount (or amountOutstanding if partially paid before)
  - Register EACH payment from the bank statement as a separate payment call

  SUPPLIER INVOICES (outgoing bank payments):
  - Look up outgoing payment types: GET /ledger/paymentTypeOut?fields=id,description
  - Register: POST /supplierInvoice/SINV_ID/:addPayment?paymentType=PT_ID&amount=AMOUNT&paymentDate=DATE&partialPayment=true with body="{}"
    NOTE: This is POST (not PUT), endpoint is /:addPayment (not /:payment), param is "amount" (not "paidAmount")
  - If NO supplier invoices exist in the system, you CANNOT create them via API.
    Instead, create payment vouchers for each outgoing payment:
    POST /ledger/voucher with postings: debit 2400 (Leverandørgjeld) + credit 1920 (Bank)
    CRITICAL: When posting to account 2400, you MUST include "supplier":{"id":SUPPLIER_ID} on that posting!
    Look up suppliers first: GET /supplier?name=KEYWORD&fields=id,name
    Without the supplier ID, the voucher will get 422 "Leverandør mangler"

NON-INVOICE BANK ENTRIES (fees, interest, etc.):
  - Bank fees/charges → debit 7770 (Bank- og kortgebyr), credit 1920 (Bank)
  - Interest income → debit 1920 (Bank), credit 8050 (Annen renteinntekt)
  - Interest expense → debit 8150 (Rentekostnad), credit 1920 (Bank)
  - Look up the account ID first: GET /ledger/account?number=7770&fields=id,number,name

MATCHING RULES:
- Match by invoice number reference in bank statement description (e.g. "Faktura 1001" → invoiceNumber 1)
- Match by customer/supplier name in bank statement
- Match by amount (exact or partial)
- A bank entry might be a partial payment — register the exact bank amount, not the full invoice amount
- Process ALL entries in the bank statement CSV, not just the first few

IMPORTANT:
- Register ALL payments from the bank statement, not just one
- For each bank statement line, find the matching invoice and register the payment
- paidAmountCurrency MUST be included alongside paidAmount

STEP 5 - STOP. Do not verify or re-fetch.
""".trimIndent()

    val prompt = buildString {
        appendLine("You are an expert Norwegian accountant processing a BANK RECONCILIATION task.")
        appendLine()
        appendLine(CommonPrompts.HEADER)
        appendLine()
        appendLine(CommonPrompts.CRITICAL_RULES)
        appendLine()
        appendLine(CommonPrompts.API_BASE)
        appendLine()
        appendLine(BANK_RECONCILIATION_RECIPE)
        appendLine()
        appendLine(CommonPrompts.BANK_ACCOUNT_SETUP)
        appendLine()
        appendLine(CommonPrompts.COMMON_ACCOUNTS)
        appendLine()
        appendLine(CommonPrompts.VOUCHER_POSTING_RULES)
        appendLine()
        appendLine(CommonPrompts.FOOTER)
    }
}
