package io.eksoda.core.model

import java.time.OffsetDateTime

data class Receipt(
    val id: String,
    val merchant: Merchant,
    val store: Store?,
    val issuedAt: OffsetDateTime,
    val totalAmount: Money,
    val items: List<ReceiptItem>,
    val url: String?,
    val createdAt: OffsetDateTime
)

data class Merchant(
    val id: String,
    val name: String,
    val website: String?
)

data class Store(
    val id: String,
    val name: String,
    val address: String?,
    val city: String?
)

data class ReceiptItem(
    val id: String,
    val product: Product?,
    val description: String,
    val quantity: Double,
    val unit: String?,
    val unitPrice: Money,
    val totalPrice: Money,
    val isProduct: Boolean
)
