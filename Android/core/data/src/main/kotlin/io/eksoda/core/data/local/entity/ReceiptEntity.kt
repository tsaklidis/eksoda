package io.eksoda.core.data.local.entity

import androidx.room.Embedded
import androidx.room.Entity
import androidx.room.PrimaryKey
import java.math.BigDecimal
import java.time.OffsetDateTime

@Entity(tableName = "receipts")
data class ReceiptEntity(
    @PrimaryKey val id: String,
    val merchantId: String,
    val merchantName: String,
    val storeId: String?,
    val storeName: String?,
    val issuedAt: OffsetDateTime,
    val totalAmount: BigDecimal,
    val currency: String,
    val url: String?,
    val createdAt: OffsetDateTime
)
