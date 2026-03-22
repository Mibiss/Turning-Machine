package no.ainm.tripletex.agent

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Pure math functions for accounting calculations.
 * These replace LLM arithmetic with exact results.
 */
object Calculators {

    /** Linear depreciation: cost / years (annual) or cost / (years * 12) (monthly). */
    fun depreciation(cost: Double, years: Int, isMonthly: Boolean): Double {
        val divisor = if (isMonthly) years * 12.0 else years.toDouble()
        return roundNok(cost / divisor)
    }

    /** Gross (incl. VAT) → Net (excl. VAT). E.g. grossToNet(125.0, 25.0) = 100.0 */
    fun grossToNet(gross: Double, vatPercent: Double): Double {
        return roundNok(gross / (1.0 + vatPercent / 100.0))
    }

    /** Net (excl. VAT) → Gross (incl. VAT). E.g. netToGross(100.0, 25.0) = 125.0 */
    fun netToGross(net: Double, vatPercent: Double): Double {
        return roundNok(net * (1.0 + vatPercent / 100.0))
    }

    /** Tax provision: 22% of profit. profit = revenue - expenses (both positive). */
    fun taxProvision(revenue: Double, expenses: Double): Double {
        val profit = revenue - expenses
        return if (profit > 0) roundNok(profit * 0.22) else 0.0
    }

    /** Exchange difference: amount * (invoiceRate - paymentRate). Positive = loss, negative = gain. */
    fun exchangeDifference(amount: Double, invoiceRate: Double, paymentRate: Double): Double {
        return roundNok(amount * (invoiceRate - paymentRate))
    }

    /** Sum a list of amounts. */
    fun sum(amounts: List<Double>): Double {
        return roundNok(amounts.fold(0.0) { acc, d -> acc + d })
    }

    /** Round to 2 decimal places using HALF_UP (standard Norwegian accounting rounding). */
    fun roundNok(amount: Double): Double {
        return BigDecimal.valueOf(amount).setScale(2, RoundingMode.HALF_UP).toDouble()
    }

    /**
     * Execute a calculation by operation name. Used by the calculate tool.
     * Returns a human-readable result string.
     */
    fun execute(operation: String, params: Map<String, Any>): String {
        return try {
            when (operation) {
                "depreciation" -> {
                    val cost = (params["cost"] as Number).toDouble()
                    val years = (params["years"] as Number).toInt()
                    val isMonthly = params["is_monthly"] as? Boolean ?: false
                    val result = depreciation(cost, years, isMonthly)
                    val period = if (isMonthly) "monthly" else "annual"
                    "$result ($period depreciation of $cost over $years years)"
                }
                "vat_gross_to_net" -> {
                    val gross = (params["amount"] as Number).toDouble()
                    val vat = (params["vat_percent"] as Number).toDouble()
                    val result = grossToNet(gross, vat)
                    "$result (net amount from gross $gross at $vat% VAT)"
                }
                "vat_net_to_gross" -> {
                    val net = (params["amount"] as Number).toDouble()
                    val vat = (params["vat_percent"] as Number).toDouble()
                    val result = netToGross(net, vat)
                    "$result (gross amount from net $net at $vat% VAT)"
                }
                "tax_provision" -> {
                    val revenue = (params["revenue"] as Number).toDouble()
                    val expenses = (params["expenses"] as Number).toDouble()
                    val result = taxProvision(revenue, expenses)
                    "$result (22% tax on profit of ${roundNok(revenue - expenses)})"
                }
                "exchange_diff" -> {
                    val amount = (params["amount"] as Number).toDouble()
                    val invoiceRate = (params["invoice_rate"] as Number).toDouble()
                    val paymentRate = (params["payment_rate"] as Number).toDouble()
                    val result = exchangeDifference(amount, invoiceRate, paymentRate)
                    val type = if (result > 0) "loss (disagio)" else "gain (agio)"
                    "$result ($type on $amount units, rate changed from $invoiceRate to $paymentRate)"
                }
                "sum" -> {
                    @Suppress("UNCHECKED_CAST")
                    val amounts = (params["amounts"] as List<Number>).map { it.toDouble() }
                    val result = sum(amounts)
                    "$result (sum of ${amounts.size} amounts)"
                }
                else -> "Error: Unknown operation '$operation'. Valid: depreciation, vat_gross_to_net, vat_net_to_gross, tax_provision, exchange_diff, sum"
            }
        } catch (e: Exception) {
            "Error in $operation: ${e.message}"
        }
    }
}
