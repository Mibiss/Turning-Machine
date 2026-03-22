package no.ainm.tripletex.agent

import no.ainm.tripletex.agent.prompts.*

/**
 * Maps each TaskType to its TaskConfig (prompt + tools + model + maxIterations).
 */
object TaskConfigRegistry {

    fun getConfig(taskType: TaskType, model: String): TaskConfig {
        val tools = getTools(taskType)
        return TaskConfig(
            taskType = taskType,
            systemPrompt = getPrompt(taskType),
            tools = tools,
            toolsWithCache = ToolDefinitions.withCache(tools),
            model = model,
            maxIterations = getMaxIterations(taskType),
        )
    }

    private fun getPrompt(taskType: TaskType): String = when (taskType) {
        TaskType.EMPLOYEE_ONBOARDING -> EmployeeOnboardingPrompt.prompt
        TaskType.CUSTOMER_CREATE -> CustomerCreatePrompt.prompt
        TaskType.SUPPLIER_CREATE -> SupplierCreatePrompt.prompt
        TaskType.INVOICE_OUTGOING -> InvoiceOutgoingPrompt.prompt
        TaskType.CREDIT_NOTE -> CreditNotePrompt.prompt
        TaskType.PAYMENT_REGISTRATION -> PaymentRegistrationPrompt.prompt
        TaskType.SUPPLIER_INVOICE -> SupplierInvoicePrompt.prompt
        TaskType.VOUCHER_MANUAL -> VoucherManualPrompt.prompt
        TaskType.EXPENSE_RECEIPT -> ExpenseReceiptPrompt.prompt
        TaskType.LEDGER_ERROR_CORRECTION -> LedgerErrorCorrectionPrompt.prompt
        TaskType.PROJECT_SETUP -> ProjectSetupPrompt.prompt
        TaskType.TRAVEL_EXPENSE -> TravelExpensePrompt.prompt
        TaskType.TIME_REGISTRATION -> TimeRegistrationPrompt.prompt
        TaskType.SALARY_PAYROLL -> SalaryPayrollPrompt.prompt
        TaskType.MONTHLY_YEAR_END_CLOSING -> MonthlyYearEndClosingPrompt.prompt
        TaskType.LEDGER_ANALYSIS -> LedgerAnalysisPrompt.prompt
        TaskType.FOREIGN_CURRENCY -> ForeignCurrencyPrompt.prompt
        TaskType.PAYMENT_REVERSAL -> PaymentReversalPrompt.prompt
        TaskType.BANK_RECONCILIATION -> BankReconciliationPrompt.prompt
        TaskType.ACCOUNTING_DIMENSIONS -> AccountingDimensionsPrompt.prompt
        TaskType.GENERAL -> GeneralPrompt.prompt
    }

    private fun getTools(taskType: TaskType) = when (taskType) {
        // Tasks needing DELETE
        TaskType.TRAVEL_EXPENSE -> ToolDefinitions.readWriteDeleteTools
        TaskType.TIME_REGISTRATION -> ToolDefinitions.readWriteDeleteTools

        // Tasks needing runtime math (calculate tool)
        TaskType.MONTHLY_YEAR_END_CLOSING -> ToolDefinitions.readWriteWithCalcTools
        TaskType.FOREIGN_CURRENCY -> ToolDefinitions.readWriteWithCalcTools
        TaskType.SUPPLIER_INVOICE -> ToolDefinitions.readWriteWithCalcTools
        TaskType.PROJECT_SETUP -> ToolDefinitions.readWriteWithCalcTools
        TaskType.LEDGER_ERROR_CORRECTION -> ToolDefinitions.readWriteWithCalcTools
        TaskType.EXPENSE_RECEIPT -> ToolDefinitions.readWriteWithCalcTools

        // GENERAL fallback gets all tools
        TaskType.GENERAL -> ToolDefinitions.allTools

        // Most tasks only need GET/POST/PUT/docs
        else -> ToolDefinitions.readWriteTools
    }

    private fun getMaxIterations(taskType: TaskType) = when (taskType) {
        // Simple tasks need fewer iterations
        TaskType.CUSTOMER_CREATE -> 10
        TaskType.SUPPLIER_CREATE -> 10
        TaskType.CREDIT_NOTE -> 10
        TaskType.PAYMENT_REGISTRATION -> 15
        TaskType.PAYMENT_REVERSAL -> 15
        TaskType.ACCOUNTING_DIMENSIONS -> 15
        TaskType.VOUCHER_MANUAL -> 15
        TaskType.BANK_RECONCILIATION -> 25

        // Medium complexity
        TaskType.INVOICE_OUTGOING -> 25
        TaskType.SUPPLIER_INVOICE -> 20
        TaskType.EXPENSE_RECEIPT -> 20
        TaskType.PROJECT_SETUP -> 25
        TaskType.SALARY_PAYROLL -> 20
        TaskType.FOREIGN_CURRENCY -> 20
        TaskType.LEDGER_ERROR_CORRECTION -> 25

        // Complex multi-step tasks
        TaskType.EMPLOYEE_ONBOARDING -> 12
        TaskType.TRAVEL_EXPENSE -> 25
        TaskType.TIME_REGISTRATION -> 25
        TaskType.MONTHLY_YEAR_END_CLOSING -> 25
        TaskType.LEDGER_ANALYSIS -> 25

        // Fallback
        TaskType.GENERAL -> 25
    }
}
