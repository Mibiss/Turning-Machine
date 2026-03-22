package no.ainm.tripletex.agent

/**
 * Persists key-value pairs across agent turns.
 * Values are extracted from tool responses and injected into every subsequent message.
 */
class Scratchpad {
    private val values = mutableMapOf<String, String>()

    fun extract(toolResponse: String) {
        val revenuePattern = Regex(""">>> TOTAL REVENUE:\s*([\d.]+)""")
        revenuePattern.find(toolResponse)?.let {
            values["TOTAL_REVENUE"] = it.groupValues[1]
        }
        val expensePattern = Regex(""">>> TOTAL EXPENSES:\s*([\d.]+)""")
        expensePattern.find(toolResponse)?.let {
            values["TOTAL_EXPENSES"] = it.groupValues[1]
        }
        val profitPattern = Regex("""PROFIT \(revenue - expenses\):\s*([-\d.]+)""")
        profitPattern.find(toolResponse)?.let {
            values["PROFIT"] = it.groupValues[1]
        }
        val taxPattern = Regex("""TAX PROVISION at 22%:\s*([\d.]+)""")
        taxPattern.find(toolResponse)?.let {
            values["TAX_PROVISION_ESTIMATE"] = it.groupValues[1]
        }
    }

    fun reminder(): String? {
        if (values.isEmpty()) return null
        return values.entries.joinToString(", ") { "${it.key}=${it.value}" }
            .let { "\n[SCRATCHPAD REMINDER: $it]" }
    }
}
