package io.eksoda.core.data.local.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import java.math.BigDecimal

@Entity(
    tableName = "receipt_items",
    foreignKeys = [
        ForeignKey(
            entity = ReceiptEntity::class,
            parentColumns = ["id"],
            childColumns = ["receiptId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("receiptId")]
)
data class ReceiptItemEntity(
    @PrimaryKey val id: String,
    val receiptId: String,
    val lineType: String,
    val description: String,
    val quantity: Double?,
    val unit: String?,
    val unitPriceAmount: BigDecimal?,
    val totalPriceAmount: BigDecimal,
    val currency: String,
    val productId: String?,
    val isProduct: Boolean
)
