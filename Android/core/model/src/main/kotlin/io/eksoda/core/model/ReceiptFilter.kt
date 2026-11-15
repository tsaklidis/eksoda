package io.eksoda.core.model

import java.time.LocalDate

data class ReceiptFilter(
    val query: String? = null,
    val merchantId: String? = null,
    val categoryId: String? = null,
    val issuedFrom: LocalDate? = null,
    val issuedTo: LocalDate? = null,
    val minAmount: Money? = null,
    val maxAmount: Money? = null,
    val isExcludedFromAnalytics: Boolean? = null,
    val ordering: ReceiptOrdering = ReceiptOrdering.ISSUED_AT_DESC
)

enum class ReceiptOrdering(val value: String) {
    ISSUED_AT_DESC("-issued_at"),
    ISSUED_AT_ASC("issued_at"),
    AMOUNT_DESC("-gross_total"),
    AMOUNT_ASC("gross_total")
}
