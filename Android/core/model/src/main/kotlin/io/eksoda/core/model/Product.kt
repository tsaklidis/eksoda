package io.eksoda.core.model

data class Product(
    val id: String,
    val name: String,
    val category: Category?,
    val brand: String?,
    val unit: String?,
    val lastPrice: Money?,
    val lastPriceAt: java.time.OffsetDateTime?,
    val isReviewed: Boolean
)
