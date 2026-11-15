package io.eksoda.core.data.local.dao

import androidx.paging.PagingSource
import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import io.eksoda.core.data.local.entity.ReceiptEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ReceiptDao {
    @Query("SELECT * FROM receipts ORDER BY issuedAt DESC")
    fun getReceipts(): PagingSource<Int, ReceiptEntity>

    @Query("SELECT * FROM receipts WHERE id = :id")
    fun getReceipt(id: String): Flow<ReceiptEntity?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertReceipts(receipts: List<ReceiptEntity>)

    @Query("DELETE FROM receipts")
    suspend fun clearAll()
}
