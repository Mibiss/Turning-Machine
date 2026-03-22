package no.ainm.tripletex.agent

import no.ainm.tripletex.FileAttachment

/**
 * Keyword-based multilingual task classifier.
 * Zero cost, zero latency, deterministic.
 * Misclassification safely falls back to GENERAL.
 */
object TaskClassifier {

    private const val THRESHOLD = 8

    fun classify(prompt: String, files: List<FileAttachment> = emptyList()): TaskType {
        val text = prompt.lowercase()
        val hasFiles = files.isNotEmpty()
        val hasReceipt = files.any { f ->
            val n = f.filename.lowercase()
            n.contains("kvittering") || n.contains("receipt") || n.contains("quittung") || n.contains("recibo")
        }
        val hasPdf = files.any { it.mimeType == "application/pdf" }
        val hasImage = files.any { it.mimeType.startsWith("image/") }
        val hasCsv = files.any { f ->
            f.filename.lowercase().endsWith(".csv") || f.mimeType.contains("csv")
        }

        // Pass 1: Structural signals (file attachments)
        // CSV + bank/reconciliation keywords → bank reconciliation
        if (hasCsv && matchesBankReconciliation(text)) return TaskType.BANK_RECONCILIATION

        if (hasReceipt || ((hasPdf || hasImage) && matchesReceipt(text))) {
            // Could be expense receipt or supplier invoice
            if (matchesSupplierInvoice(text)) return TaskType.SUPPLIER_INVOICE
            return TaskType.EXPENSE_RECEIPT
        }

        // PDF with supplier invoice keywords → supplier invoice
        if (hasPdf && matchesSupplierInvoice(text)) return TaskType.SUPPLIER_INVOICE

        // Pass 2: Keyword scoring — score every task type, pick highest
        val scores = TaskType.entries.associateWith { scoreTaskType(it, text, hasFiles) }
        val best = scores.maxByOrNull { it.value } ?: return TaskType.GENERAL
        if (best.value < THRESHOLD) return TaskType.GENERAL

        // Disambiguation rules
        return disambiguate(best.key, text, scores)
    }

    private fun matchesReceipt(text: String): Boolean {
        return text.containsAny("kvittering", "receipt", "quittung", "recibo", "reçu", "registrer kostnad", "register cost")
    }

    private fun matchesSupplierInvoice(text: String): Boolean {
        return text.containsAny("leverandørfaktura", "leverandorfaktura", "supplier invoice", "lieferantenrechnung",
            "factura proveedor", "factura de proveedor", "fatura de fornecedor", "facture fournisseur") ||
                (text.containsAny("leverandør", "leverandor", "supplier", "lieferant", "proveedor", "fournisseur", "fornecedor") &&
                        text.containsAny("faktura", "invoice", "rechnung", "factura", "facture", "fatura"))
    }

    private fun matchesBankReconciliation(text: String): Boolean {
        return text.containsAny("avstem", "reconcil", "abstimm", "rapproch", "concilia",
            "bankutskrift", "bank statement", "kontoauszug", "relevé bancaire", "extracto bancario", "extrato bancário",
            "bankavstemming", "bank reconciliation")
    }

    private fun scoreTaskType(type: TaskType, text: String, hasFiles: Boolean): Int {
        return when (type) {
            TaskType.SALARY_PAYROLL -> text.scoreKeywords(
                w(10, "lønn", "lønnskjøring", "lønnsslipp", "salary", "payroll", "gehalt", "salario", "salaire", "salário"),
                w(8, "fastlønn", "timelønn", "bonus/tantieme", "nómina", "paie", "folha de pagamento"),
                w(5, "salary/transaction", "/salary"),
                w(3, "payslip", "lønnsutbetaling", "gehaltsabrechnung", "bulletin de paie", "fiche de paie", "holerite"),
            )
            TaskType.EMPLOYEE_ONBOARDING -> text.scoreKeywords(
                w(10, "ansatt", "employee", "mitarbeiter", "empleado", "employé", "empregado", "funcionário"),
                w(8, "onboarding", "ansettelse", "arbeidskontrakt", "employment contract", "arbeitsvertrag",
                    "contrat de travail", "contrato de trabajo", "contrato de trabalho"),
                w(6, "stillingsprosent", "årslønn", "arbeidstid", "annual salary", "working hours",
                    "embauche", "recrutement", "contratación"),
                w(5, "personnummer", "fødselsnummer", "national identity"),
                w(4, "avdeling", "department", "abteilung", "département", "departamento"),
            )
            TaskType.CUSTOMER_CREATE -> text.scoreKeywords(
                w(10, "opprett kunde", "create customer", "ny kunde", "new customer", "neuer kunde",
                    "créer client", "nouveau client", "crear cliente", "nuevo cliente", "criar cliente", "novo cliente"),
                w(8, "iscustomer"),
                // "kunde"/"client" alone scores lower to avoid matching "kundefaktura"/"facture client"
                w(4, "kunde", "customer", "kund", "client", "cliente"),
            )
            TaskType.SUPPLIER_CREATE -> text.scoreKeywords(
                w(10, "leverandør", "supplier", "lieferant", "proveedor", "fournisseur", "fornecedor"),
                w(8, "opprett leverandør", "create supplier", "ny leverandør", "new supplier",
                    "neuer lieferant", "créer fournisseur", "nouveau fournisseur",
                    "crear proveedor", "nuevo proveedor", "novo fornecedor", "criar fornecedor"),
                // Disambiguation: must NOT have invoice keywords
            )
            TaskType.INVOICE_OUTGOING -> text.scoreKeywords(
                w(10, "faktura", "invoice", "rechnung", "factura", "facture", "fatura"),
                w(8, "utgående faktura", "outgoing invoice", "ausgangsrechnung",
                    "facture sortante", "factura saliente", "fatura de saída"),
                w(6, "ordrelinje", "order line", "orderline", "ligne de commande", "línea de pedido"),
                w(5, "produkt", "product", "vare", "produit", "producto"),
                w(4, "mva", "vat", "mwst", "iva", "tva"),
            )
            TaskType.CREDIT_NOTE -> text.scoreKeywords(
                w(10, "kreditnota", "credit note", "gutschrift", "nota de crédito", "note de crédit", "nota de crédito"),
                w(8, "kreditere", "creditnote", "createcreditnote"),
            )
            TaskType.PAYMENT_REGISTRATION -> text.scoreKeywords(
                w(10, "registrer betaling", "register payment", "zahlung registrieren",
                    "enregistrer paiement", "registrar pago", "registrar pagamento"),
                w(8, "betaling", "payment", "zahlung", "pago", "paiement", "pagamento"),
                w(5, "betalt", "paid", "bezahlt", "pagado", "payé"),
                // Only if combined with invoice context but NOT reversal
            )
            TaskType.SUPPLIER_INVOICE -> text.scoreKeywords(
                w(10, "leverandørfaktura", "leverandorfaktura", "supplier invoice", "lieferantenrechnung",
                    "factura de proveedor", "fatura de fornecedor", "facture fournisseur"),
                w(8, "inngående faktura", "inngaende faktura", "incoming invoice", "eingangsrechnung",
                    "facture entrante", "factura entrante", "fatura de entrada"),
                w(6, "supplierinvoice", "/supplierinvoice", "fornecedor",
                    "leverandor", "inngaende"),
            )
            TaskType.VOUCHER_MANUAL -> text.scoreKeywords(
                w(10, "bilag", "voucher", "journal entry", "buchungssatz",
                    "écriture comptable", "pièce comptable", "asiento contable", "lançamento contábil"),
                w(8, "manuell postering", "manual posting", "manuelle buchung",
                    "écriture manuelle", "asiento manual", "lançamento manual"),
                w(6, "postering", "posting", "buchung", "asiento", "écriture", "lançamento"),
                w(5, "debet", "kredit", "debit", "credit", "soll", "haben", "débit", "crédit", "débito", "crédito"),
            )
            TaskType.EXPENSE_RECEIPT -> text.scoreKeywords(
                w(10, "kvittering", "receipt", "quittung", "recibo", "reçu"),
                w(8, "registrer kostnad", "register cost", "register expense",
                    "enregistrer dépense", "registrar gasto", "registrar despesa"),
                w(6, "utlegg", "expense", "ausgabe", "gasto", "dépense", "despesa", "note de frais"),
            )
            TaskType.LEDGER_ERROR_CORRECTION -> text.scoreKeywords(
                w(10, "feilretting", "error correction", "fehlerkorrektur",
                    "corrección de errores", "correction d'erreur", "correção de erros"),
                w(10, "korrigering", "correction", "korrektur", "corriger", "corrigez", "corregir", "corrigir"),
                w(8, "feil", "error", "fehler", "erreur", "erro"),
                w(6, "duplisert", "duplicate", "doppelt", "duplicado", "en double", "doublé", "duplicata"),
                w(6, "feil konto", "wrong account", "falsches konto", "cuenta incorrecta", "mauvais compte", "conta errada"),
                w(5, "reversere", "reverse", "stornieren", "inverser", "revertir", "reverter"),
                w(5, "manquante", "missing", "fehlend", "faltante"),
            )
            TaskType.PROJECT_SETUP -> text.scoreKeywords(
                w(10, "prosjektsyklus", "project cycle", "projektzyklus",
                    "ciclo de proyecto", "cycle de projet", "ciclo de projeto"),
                w(10, "prosjekt", "project", "projekt", "proyecto", "projet", "projeto"),
                w(8, "opprett prosjekt", "create project", "nytt prosjekt", "new project",
                    "créer projet", "nouveau projet", "crear proyecto", "nuevo proyecto"),
                w(6, "aktivitet", "activity", "aktivität", "actividad", "activité", "atividade"),
                w(5, "budsjett", "budget", "presupuesto", "orçamento"),
                w(4, "prosjektleder", "project manager", "chef de projet", "jefe de proyecto"),
            )
            TaskType.TRAVEL_EXPENSE -> text.scoreKeywords(
                w(10, "reiseregning", "travel expense", "reisekostenabrechnung",
                    "gastos de viaje", "frais de déplacement", "despesas de viagem", "note de frais de voyage"),
                w(10, "reise", "travel", "voyage", "viaje", "viagem"),
                w(8, "diett", "per diem", "tagesgeld", "dieta", "indemnité journalière"),
                w(6, "kjøregodtgjørelse", "mileage", "kilometergeld",
                    "indemnité kilométrique", "kilometraje", "quilometragem"),
                w(6, "overnatting", "accommodation", "unterkunft", "alojamiento", "hébergement", "hospedagem"),
                w(5, "flyreise", "flight", "flug", "vuelo", "vol", "voo"),
            )
            TaskType.TIME_REGISTRATION -> text.scoreKeywords(
                w(10, "timeregistrering", "time registration", "zeiterfassung",
                    "enregistrement du temps", "registro de tiempo", "registro de horas"),
                w(10, "timer", "hours", "stunden", "horas", "heures"),
                w(8, "timesheet", "timeliste", "feuille de temps", "hoja de horas", "folha de horas"),
                w(5, "fakturerbar", "chargeable", "abrechenbar", "facturable"),
            )
            TaskType.MONTHLY_YEAR_END_CLOSING -> text.scoreKeywords(
                w(10, "månedsavslutning", "årsavslutning", "month-end closing", "year-end closing",
                    "encerramento mensal", "encerramento anual"),
                w(10, "monatsabschluss", "jahresabschluss", "cierre mensual", "cierre anual", "clôture",
                    "clôture mensuelle", "clôture annuelle"),
                w(8, "avskrivning", "depreciation", "abschreibung", "depreciación", "amortissement", "depreciação"),
                w(8, "periodisering", "accrual", "rechnungsabgrenzung", "régularisation", "devengo"),
                w(6, "skatteavsetning", "tax provision", "steuerrückstellung", "provision fiscale", "provisión fiscal"),
                w(6, "lønnsavsetning", "salary accrual", "gehaltsrückstellung"),
                w(5, "forskuddsbetalt", "prepaid", "vorausbezahlt", "prépayé", "prepago"),
            )
            TaskType.LEDGER_ANALYSIS -> text.scoreKeywords(
                w(10, "analyse", "analysis", "análisis", "análise", "analice", "analysieren", "analyser", "analisar"),
                w(10, "libro mayor", "hovedbok", "general ledger", "hauptbuch", "grand livre", "livro razão"),
                w(8, "trend", "utvikling", "development", "entwicklung", "tendance", "tendencia"),
                w(8, "største økning", "biggest increase", "größte steigerung", "plus grande augmentation",
                    "mayor aumento", "mayor incremento", "maior aumento", "maior incremento"),
                w(6, "sammenlign", "compare", "vergleich", "comparar", "comparer"),
                w(6, "økning", "increase", "incremento", "aumento", "augmentation", "steigerung", "crescimento"),
                w(5, "periode", "period", "zeitraum", "período", "période"),
                w(5, "kostnader", "gastos", "costs", "ausgaben", "dépenses", "custos", "despesas"),
            )
            TaskType.FOREIGN_CURRENCY -> text.scoreKeywords(
                w(10, "valuta", "currency", "währung", "moneda", "devise", "moeda"),
                w(10, "disagio", "agio"),
                w(8, "valutatap", "valutagevinst", "exchange loss", "exchange gain",
                    "perte de change", "gain de change", "pérdida cambiaria", "ganancia cambiaria"),
                w(8, "vekslingskurs", "exchange rate", "wechselkurs", "tipo de cambio", "taux de change", "taxa de câmbio"),
                w(6, "utenlandsk", "foreign", "ausländisch", "extranjero", "étranger", "estrangeiro"),
            )
            TaskType.PAYMENT_REVERSAL -> text.scoreKeywords(
                w(10, "tilbakeføre betaling", "reverse payment", "zahlung stornieren",
                    "reverter pagamento", "revertir pago"),
                w(10, "annuler le paiement", "annullere betaling", "cancel payment",
                    "anular pagamento", "anular pago", "cancelar pagamento"),
                w(8, "annuler", "annullere", "cancel", "stornieren", "anular", "cancelar"),
                w(8, "reverser", "reverse", "zurückgebucht", "zurückbuchen", "retourné", "retourner",
                    "devolvido", "devolver", "returnert", "returnere"),
                w(6, "tilbakeføring", "reversal", "storno", "anulación", "annulation", "estorno"),
            )
            TaskType.BANK_RECONCILIATION -> text.scoreKeywords(
                w(10, "bankavstemming", "bank reconciliation", "bankabstimmung",
                    "rapprochement bancaire", "conciliación bancaria", "conciliação bancária"),
                w(10, "avstem", "reconcile", "abstimm", "rapprocher", "conciliar", "concilia"),
                w(8, "bankutskrift", "bank statement", "kontoauszug",
                    "relevé bancaire", "extracto bancario", "extrato bancário"),
                w(8, "bankkonto", "bank account", "bankkonto", "compte bancaire", "cuenta bancaria", "conta bancária"),
                w(5, "avstemming", "reconciliation", "abstimmung", "rapprochement", "conciliación", "conciliação"),
            )
            TaskType.ACCOUNTING_DIMENSIONS -> text.scoreKeywords(
                w(10, "dimensjon", "dimension"),
                w(10, "koststed", "cost center", "kostenstelle", "centro de costos", "centre de coûts", "centro de custos"),
                w(8, "accountingdimension", "regnskapsdimensjon"),
                w(8, "dimension value", "dimensjonsverdi", "dimensionswert", "valeur de dimension"),
                w(6, "custom dimension", "egendefinert dimensjon", "benutzerdefinierte dimension"),
            )
            TaskType.GENERAL -> 0 // Fallback never wins by score
        }
    }

    /** Disambiguation: resolve conflicts between similar task types. */
    private fun disambiguate(best: TaskType, text: String, scores: Map<TaskType, Int>): TaskType {
        // Bank reconciliation: "extracto bancario" + "concilia" or CSV context → BANK_RECONCILIATION
        if ((best == TaskType.INVOICE_OUTGOING || best == TaskType.SUPPLIER_INVOICE || best == TaskType.PAYMENT_REGISTRATION) &&
            matchesBankReconciliation(text)) {
            return TaskType.BANK_RECONCILIATION
        }

        // "leverandør"/"leverandor" + "faktura" → SUPPLIER_INVOICE, not SUPPLIER_CREATE or INVOICE_OUTGOING
        if (best == TaskType.SUPPLIER_CREATE &&
            text.containsAny("faktura", "invoice", "rechnung", "factura", "facture")) {
            return TaskType.SUPPLIER_INVOICE
        }
        if (best == TaskType.INVOICE_OUTGOING &&
            text.containsAny("leverandør", "leverandor", "supplier", "lieferant", "proveedor", "fournisseur", "fornecedor",
                "inngående", "inngaende", "incoming", "eingangs")) {
            return TaskType.SUPPLIER_INVOICE
        }

        // "betaling" + "annuler"/"tilbakeføre" → PAYMENT_REVERSAL, not PAYMENT_REGISTRATION
        if (best == TaskType.PAYMENT_REGISTRATION &&
            text.containsAny("annuler", "annullere", "tilbakeføre", "reverse", "cancel", "stornieren", "anular")) {
            return TaskType.PAYMENT_REVERSAL
        }

        // "faktura" + "reverser"/"returnert"/"annuler" → PAYMENT_REVERSAL, not INVOICE_OUTGOING
        if (best == TaskType.INVOICE_OUTGOING &&
            text.containsAny("reverser", "returnert", "tilbakeføre", "zurückgebucht", "retourné",
                "annuler", "annullere", "stornieren", "devolvido", "reverse")) {
            return TaskType.PAYMENT_REVERSAL
        }

        // "pago"/"payment" + "factura"/"invoice" + "cree"/"create" → INVOICE_OUTGOING (reminder charge tasks)
        if (best == TaskType.PAYMENT_REGISTRATION &&
            text.containsAny("factura", "faktura", "rechnung", "invoice", "facture", "fatura") &&
            text.containsAny("cree", "créer", "create", "erstell", "opprett", "recordatorio", "reminder", "mahnung", "rappel")) {
            return TaskType.INVOICE_OUTGOING
        }

        // "betaling" + "valuta"/"currency" → FOREIGN_CURRENCY, not PAYMENT_REGISTRATION
        if (best == TaskType.PAYMENT_REGISTRATION &&
            text.containsAny("valuta", "currency", "währung", "disagio", "agio", "exchange rate", "vekslingskurs")) {
            return TaskType.FOREIGN_CURRENCY
        }

        // "prosjekt" + "timer"/"hours" → TIME_REGISTRATION only if time score is strictly higher
        // (avoids overriding full project cycles that include time registration as a sub-step)
        if (best == TaskType.PROJECT_SETUP && (scores[TaskType.TIME_REGISTRATION] ?: 0) > (scores[best] ?: 0)) {
            return TaskType.TIME_REGISTRATION
        }

        // "prosjekt" + "analyse"/"ledger" → LEDGER_ANALYSIS if it also has analysis keywords
        if (best == TaskType.PROJECT_SETUP &&
            text.containsAny("analice", "analyse", "analysis", "analyser", "analysieren", "analisar",
                "libro mayor", "hovedbok", "general ledger", "hauptbuch") &&
            text.containsAny("økning", "increase", "incremento", "aumento", "augmentation", "steigerung")) {
            return TaskType.LEDGER_ANALYSIS
        }

        // "feil" + "bilag"/"voucher" → LEDGER_ERROR_CORRECTION, not VOUCHER_MANUAL
        if (best == TaskType.VOUCHER_MANUAL &&
            text.containsAny("feil", "error", "fehler", "erreur", "erro",
                "korriger", "correct", "korrektur", "corriger", "corregir", "corrigir")) {
            return TaskType.LEDGER_ERROR_CORRECTION
        }

        // "dimension" + "voucher" → ACCOUNTING_DIMENSIONS, not VOUCHER_MANUAL
        if (best == TaskType.VOUCHER_MANUAL &&
            text.containsAny("dimension", "dimensjon")) {
            return TaskType.ACCOUNTING_DIMENSIONS
        }

        // "ansatt" + "lønn" → depends on context: if creating employee, it's onboarding
        // If just running salary, it's payroll. Use score comparison.
        if (best == TaskType.EMPLOYEE_ONBOARDING && (scores[TaskType.SALARY_PAYROLL] ?: 0) > (scores[best] ?: 0)) {
            // Only override if there are no onboarding-specific keywords
            if (!text.containsAny("onboarding", "ansettelse", "ansett", "kontrakt", "contract", "vertrag")) {
                return TaskType.SALARY_PAYROLL
            }
        }

        return best
    }

    // Helper: weighted keyword group
    private data class WeightedKeywords(val weight: Int, val keywords: List<String>)

    private fun w(weight: Int, vararg keywords: String) = WeightedKeywords(weight, keywords.toList())

    private fun String.scoreKeywords(vararg groups: WeightedKeywords): Int {
        var score = 0
        for (group in groups) {
            for (keyword in group.keywords) {
                if (this.contains(keyword)) {
                    score += group.weight
                    break // Only count each weight group once
                }
            }
        }
        return score
    }

    private fun String.containsAny(vararg keywords: String): Boolean {
        return keywords.any { this.contains(it) }
    }
}
