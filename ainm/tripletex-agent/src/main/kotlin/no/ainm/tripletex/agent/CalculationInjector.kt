package no.ainm.tripletex.agent

/**
 * Pre-computes numeric values from the prompt text and appends them to the user message.
 * Only runs for task types that need it. If regex fails to extract, no injection (safe default).
 */
object CalculationInjector {

    private val NEEDS_INJECTION = setOf(
        TaskType.MONTHLY_YEAR_END_CLOSING,
        TaskType.FOREIGN_CURRENCY,
        TaskType.SUPPLIER_INVOICE,
    )

    fun inject(prompt: String, taskType: TaskType): String {
        if (taskType !in NEEDS_INJECTION) return prompt

        val computations = mutableListOf<String>()

        when (taskType) {
            TaskType.MONTHLY_YEAR_END_CLOSING -> {
                extractDepreciation(prompt)?.let { computations.add(it) }
                extractVatComputation(prompt)?.let { computations.add(it) }
            }
            TaskType.FOREIGN_CURRENCY -> {
                extractExchangeDiff(prompt)?.let { computations.add(it) }
            }
            TaskType.SUPPLIER_INVOICE -> {
                extractVatComputation(prompt)?.let { computations.add(it) }
            }
            else -> {}
        }

        if (computations.isEmpty()) return prompt

        return buildString {
            append(prompt)
            append("\n\n[PRE-COMPUTED VALUES:\n")
            computations.forEachIndexed { i, c ->
                append("  ${i + 1}. $c\n")
            }
            append("]")
        }
    }

    private fun extractDepreciation(text: String): String? {
        // Match patterns like "194750 NOK over 9 years" or "266350 kr / 5 år"
        // Also: "anskaffelseskost 194750" + "levetid 9 år"
        val costPattern = Regex(
            """(?:anskaffelseskost|acquisition cost|anschaffungskosten|cost|kostpris|verdi)\s*[:=]?\s*([\d\s.,]+)\s*(?:NOK|kr|€|\$)?""",
            RegexOption.IGNORE_CASE
        )
        val yearsPattern = Regex(
            """(?:levetid|useful life|nutzungsdauer|vida útil|durée de vie|over)\s*[:=]?\s*(\d+)\s*(?:år|years|jahre|años|ans|year)""",
            RegexOption.IGNORE_CASE
        )
        val isMonthly = text.lowercase().let {
            it.contains("månedlig") || it.contains("monthly") || it.contains("monatlich") ||
                    it.contains("mensual") || it.contains("mensuel") || it.contains("per måned") ||
                    it.contains("per month")
        }

        val costMatch = costPattern.find(text) ?: return null
        val yearsMatch = yearsPattern.find(text) ?: return null

        val cost = costMatch.groupValues[1].replace(Regex("[\\s]"), "").replace(",", ".").toDoubleOrNull() ?: return null
        val years = yearsMatch.groupValues[1].toIntOrNull() ?: return null

        val result = Calculators.depreciation(cost, years, isMonthly)
        val period = if (isMonthly) "monthly" else "annual"
        return "Depreciation ($period): $cost / ${if (isMonthly) "${years}×12=${years * 12}" else "$years"} = $result NOK"
    }

    private fun extractVatComputation(text: String): String? {
        // Match patterns like "12500 inkl. mva" or "gross 12500 at 25%"
        val grossPattern = Regex(
            """([\d\s.,]+)\s*(?:NOK|kr)?\s*(?:inkl\.?\s*(?:mva|moms|vat|mwst)|gross|brutto|inkludert\s+mva)""",
            RegexOption.IGNORE_CASE
        )
        val grossMatch = grossPattern.find(text) ?: return null
        val gross = grossMatch.groupValues[1].replace(Regex("[\\s]"), "").replace(",", ".").toDoubleOrNull() ?: return null

        // Determine VAT rate (default 25% for Norwegian accounting)
        val vatRate = when {
            text.lowercase().contains("12%") || text.lowercase().contains("lav sats") -> 12.0
            text.lowercase().contains("15%") || text.lowercase().contains("middels sats") -> 15.0
            else -> 25.0
        }

        val net = Calculators.grossToNet(gross, vatRate)
        val vat = Calculators.roundNok(gross - net)
        return "VAT calculation: gross=$gross, net=$net, VAT($vatRate%)=$vat"
    }

    private fun extractExchangeDiff(text: String): String? {
        // Match patterns for exchange rates
        val ratePattern = Regex(
            """(?:kurs|rate|taux|tipo)\s*[:=]?\s*([\d.,]+)""",
            RegexOption.IGNORE_CASE
        )
        val rates = ratePattern.findAll(text).mapNotNull {
            it.groupValues[1].replace(",", ".").toDoubleOrNull()
        }.toList()

        if (rates.size < 2) return null

        // Try to find the amount
        val amountPattern = Regex(
            """([\d\s.,]+)\s*(?:USD|EUR|GBP|SEK|DKK|CHF)""",
            RegexOption.IGNORE_CASE
        )
        val amountMatch = amountPattern.find(text)
        val amount = amountMatch?.groupValues?.get(1)?.replace(Regex("[\\s]"), "")?.replace(",", ".")?.toDoubleOrNull()
            ?: return null

        val invoiceRate = rates[0]
        val paymentRate = rates[1]
        val diff = Calculators.exchangeDifference(amount, invoiceRate, paymentRate)
        val type = if (diff > 0) "loss (disagio)" else "gain (agio)"
        return "Exchange difference: $amount × ($invoiceRate - $paymentRate) = $diff ($type)"
    }
}
