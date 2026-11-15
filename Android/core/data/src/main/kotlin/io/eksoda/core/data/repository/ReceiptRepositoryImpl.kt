package io.eksoda.core.data.repository

import androidx.paging.ExperimentalPagingApi
import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.map
import io.eksoda.core.data.local.EksodaDatabase
import io.eksoda.core.data.local.entity.ReceiptEntity
import io.eksoda.core.data.paging.ReceiptRemoteMediator
import io.eksoda.core.model.Merchant
import io.eksoda.core.model.Money
import io.eksoda.core.model.Receipt
import io.eksoda.core.network.api.ReceiptApi
import io.eksoda.core.network.model.ReceiptImportRequest
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.math.BigDecimal
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReceiptRepositoryImpl @Inject constructor(
    private val receiptApi: ReceiptApi,
    private val database: EksodaDatabase
) : ReceiptRepository {

    @OptIn(ExperimentalPagingApi::class)
    override fun getReceipts(householdId: String): Flow<PagingData<Receipt>> {
        return Pager(
            config = PagingConfig(pageSize = 25),
            remoteMediator = ReceiptRemoteMediator(householdId, receiptApi, database),
            pagingSourceFactory = { database.receiptDao().getReceipts() }
        ).flow.map { pagingData ->
            pagingData.map { it.toDomain() }
        }
    }

    override fun getReceipt(id: String): Flow<Receipt?> {
        return database.receiptDao().getReceipt(id).map { it?.toDomain() }
    }

    override suspend fun importReceipt(url: String, householdId: String): Result<String> {
        return try {
            val response = receiptApi.importReceipt(ReceiptImportRequest(url))
            Result.success(response.id)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getImportJobs(householdId: String): Result<List<ImportJob>> {
        return try {
            val response = receiptApi.getImportJobs()
            Result.success(response.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getImportJob(id: String): Result<ImportJob> {
        return try {
            val response = receiptApi.getImportJob(id)
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun retryImport(id: String): Result<Unit> {
        return try {
            receiptApi.retryImport(id)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun deleteReceipt(id: String): Result<Unit> {
        return try {
            receiptApi.deleteReceipt(id)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun ReceiptEntity.toDomain(): Receipt {
        return Receipt(
            id = id,
            merchant = Merchant(id = merchantId, name = merchantName, website = null),
            store = if (storeId != null && storeName != null) {
                io.eksoda.core.model.Store(id = storeId, name = storeName, address = null, city = null)
            } else null,
            issuedAt = issuedAt,
            totalAmount = Money(totalAmount, currency),
            items = emptyList(),
            url = url,
            createdAt = createdAt
        )
    }

    private fun io.eksoda.core.network.model.ImportJobResponse.toDomain(): ImportJob {
        return ImportJob(
            id = id,
            status = when (status.lowercase()) {
                "completed" -> ImportStatus.COMPLETED
                "failed" -> ImportStatus.FAILED
                else -> ImportStatus.PENDING
            },
            outcome = outcome,
            submittedUrl = submitted_url,
            error = error?.message,
            receiptId = receipt_id
        )
    }
}
