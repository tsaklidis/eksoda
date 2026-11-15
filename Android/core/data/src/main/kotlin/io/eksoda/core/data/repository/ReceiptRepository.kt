package io.eksoda.core.data.repository

import androidx.paging.PagingData
import io.eksoda.core.model.ImportJob
import io.eksoda.core.model.Receipt
import kotlinx.coroutines.flow.Flow

interface ReceiptRepository {
    fun getReceipts(householdId: String): Flow<PagingData<Receipt>>
    fun getReceipt(id: String): Flow<Receipt?>
    
    suspend fun importReceipt(url: String, householdId: String): Result<String>
    suspend fun getImportJobs(householdId: String): Result<List<ImportJob>>
    suspend fun getImportJob(id: String): Result<ImportJob>
    suspend fun retryImport(id: String): Result<Unit>
    
    suspend fun deleteReceipt(id: String): Result<Unit>
}
