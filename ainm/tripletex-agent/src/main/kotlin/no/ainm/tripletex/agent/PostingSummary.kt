package no.ainm.tripletex.agent

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Auto-computes posting summaries from /ledger/posting responses.
 * Appends exact totals so the LLM doesn't need to mentally sum entries.
 */
object PostingSummary {
    private val json = Json { ignoreUnknownKeys = true }

    fun summarize(responseBody: String): String? {
        return try {
            val root = json.parseToJsonElement(responseBody).jsonObject
            val values = root["values"]?.jsonArray ?: return null
            if (values.size < 10) return null

            // Parse all postings
            data class Posting(val accountNumber: Int, val accountName: String, val amount: Double, val yearMonth: String)
            val postings = mutableListOf<Posting>()

            for (entry in values) {
                val obj = entry.jsonObject
                val account = obj["account"]?.jsonObject ?: continue
                val accountNumber = account["number"]?.jsonPrimitive?.int ?: continue
                // Support both "amount" and "amountCurrency" fields
                val amount = obj["amount"]?.jsonPrimitive?.double
                    ?: obj["amountCurrency"]?.jsonPrimitive?.double
                    ?: continue
                val name = account["name"]?.jsonPrimitive?.content ?: ""
                val date = obj["date"]?.jsonPrimitive?.content ?: ""
                val yearMonth = if (date.length >= 7) date.substring(0, 7) else ""

                postings.add(Posting(accountNumber, name, amount, yearMonth))
            }

            // Detect if data spans multiple months
            val months = postings.map { it.yearMonth }.filter { it.isNotEmpty() }.toSortedSet()
            val isMultiMonth = months.size > 1

            // Per-account totals (overall)
            val accountTotals = mutableMapOf<Int, Double>()
            val accountNames = mutableMapOf<Int, String>()
            for (p in postings) {
                accountTotals[p.accountNumber] = (accountTotals[p.accountNumber] ?: 0.0) + p.amount
                if (p.accountName.isNotBlank()) accountNames[p.accountNumber] = p.accountName
            }

            // Per-account per-month totals (for multi-month analysis)
            val accountMonthTotals = mutableMapOf<Int, MutableMap<String, Double>>()
            if (isMultiMonth) {
                for (p in postings) {
                    if (p.yearMonth.isEmpty()) continue
                    val monthMap = accountMonthTotals.getOrPut(p.accountNumber) { mutableMapOf() }
                    monthMap[p.yearMonth] = (monthMap[p.yearMonth] ?: 0.0) + p.amount
                }
            }

            buildString {
                appendLine()
                appendLine("[POSTING SUMMARY — auto-computed from ${values.size} postings]")

                // Per-account per-month breakdown (for analysis tasks)
                if (isMultiMonth) {
                    val sortedMonths = months.toList()
                    appendLine()
                    appendLine("PER-ACCOUNT MONTHLY TOTALS (expense accounts 4000-7999):")
                    val accountChanges = mutableListOf<Triple<Int, String, Double>>()
                    for ((acctNum, monthMap) in accountMonthTotals.toSortedMap()) {
                        if (acctNum !in 4000..7999) continue
                        val name = accountNames[acctNum] ?: ""
                        val monthValues = sortedMonths.map { m ->
                            val v = round2(monthMap[m] ?: 0.0)
                            "$m=$v"
                        }.joinToString(", ")
                        // Compute change between first and last month
                        val firstVal = monthMap[sortedMonths.first()] ?: 0.0
                        val lastVal = monthMap[sortedMonths.last()] ?: 0.0
                        val change = round2(lastVal - firstVal)
                        appendLine("  $acctNum $name: $monthValues (change: $change)")
                        accountChanges.add(Triple(acctNum, name, change))
                    }
                    // Pre-ranked top accounts by increase
                    val topIncreases = accountChanges.filter { it.third > 0 }.sortedByDescending { it.third }
                    if (topIncreases.isNotEmpty()) {
                        appendLine()
                        appendLine("TOP EXPENSE ACCOUNTS BY LARGEST INCREASE:")
                        for ((rank, entry) in topIncreases.withIndex()) {
                            appendLine("  ${rank + 1}. ${entry.first} ${entry.second}: change=+${entry.third}")
                        }
                    }
                }

                // Revenue/expense totals
                val revenueLines = mutableListOf<String>()
                val expenseLines = mutableListOf<String>()
                var totalRevenue = 0.0
                var totalExpenses = 0.0

                for ((acctNum, total) in accountTotals.toSortedMap()) {
                    val rounded = round2(total)
                    val name = accountNames[acctNum] ?: ""
                    when (acctNum) {
                        in 3000..3999 -> {
                            totalRevenue += total
                            revenueLines.add("  $acctNum $name: $rounded")
                        }
                        in 4000..8999 -> {
                            totalExpenses += total
                            expenseLines.add("  $acctNum $name: $rounded")
                        }
                    }
                }

                totalRevenue = round2(Math.abs(totalRevenue))
                totalExpenses = round2(totalExpenses)
                val profit = round2(totalRevenue - totalExpenses)
                val tax22 = round2(if (profit > 0) profit * 0.22 else 0.0)

                appendLine()
                appendLine("REVENUE (accounts 3000-3999, absolute values):")
                revenueLines.forEach { appendLine(it) }
                appendLine("  >>> TOTAL REVENUE: $totalRevenue")
                appendLine()
                appendLine("EXPENSES (accounts 4000-8999):")
                expenseLines.forEach { appendLine(it) }
                appendLine("  >>> TOTAL EXPENSES: $totalExpenses")
                appendLine()
                appendLine("PROFIT (revenue - expenses): $profit")
                appendLine("TAX PROVISION at 22%: $tax22")
                appendLine("[For year-end closing: use TOTAL REVENUE and TOTAL EXPENSES with the calculator tool]")
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun round2(amount: Double): Double {
        return BigDecimal.valueOf(amount).setScale(2, RoundingMode.HALF_UP).toDouble()
    }
}
