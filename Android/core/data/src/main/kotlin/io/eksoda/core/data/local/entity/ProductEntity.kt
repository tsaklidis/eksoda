package io.eksoda.core.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.math.BigDecimal
import java.time.OffsetDateTime

@Entity(tableName = "products")
data class ProductEntity(
    @PrimaryKey val id: String,
    val name: String,
    val categoryId: String?,
    val brand: String?,
    val unit: String?,
    val lastPriceAmount: BigDecimal?,
    val lastPriceCurrency: String?,
    val lastPriceAt: OffsetDateTime?,
    val isReviewed: Boolean
)
