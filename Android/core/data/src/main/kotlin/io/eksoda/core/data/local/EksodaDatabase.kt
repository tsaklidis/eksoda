package io.eksoda.core.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import io.eksoda.core.data.local.dao.ReceiptDao
import io.eksoda.core.data.local.entity.ReceiptEntity

@Database(
    entities = [
        ReceiptEntity::class
    ],
    version = 1,
    exportSchema = true
)
@TypeConverters(Converters::class)
abstract class EksodaDatabase : RoomDatabase() {
    abstract fun receiptDao(): ReceiptDao
}
