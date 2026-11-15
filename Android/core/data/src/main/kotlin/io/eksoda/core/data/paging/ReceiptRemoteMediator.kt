package io.eksoda.core.data.paging

import androidx.paging.ExperimentalPagingApi
import androidx.paging.LoadType
import androidx.paging.PagingState
import androidx.paging.RemoteMediator
import androidx.room.withTransaction
import io.eksoda.core.data.local.EksodaDatabase
import io.eksoda.core.data.local.entity.ReceiptEntity
import io.eksoda.core.network.api.ReceiptApi
import java.math.BigDecimal
import java.time.OffsetDateTime

@OptIn(ExperimentalPagingApi::class)
class ReceiptRemoteMediator(
    private val householdId: String,
    private val receiptApi: ReceiptApi,
    private val database: EksodaDatabase
) : RemoteMediator<Int, ReceiptEntity>() {

    override fun initialize(): InitializeAction {
        return InitializeAction.LAUNCH_INITIAL_REFRESH
    }

    override suspend fun load(
        loadType: LoadType,
        state: PagingState<Int, ReceiptEntity>
    ): MediatorResult {
        return try {
            val page = when (loadType) {
                LoadType.REFRESH -> 1
                LoadType.PREPEND -> return MediatorResult.Success(endOfPaginationReached = true)
                LoadType.APPEND -> {
                    val lastItem = state.lastItemOrNull()
                    if (lastItem == null) {
                        1
                    } else {
                        // This is a simplification. DRF pagination usually uses page numbers.
                        // We'd need to track the next page number from the API response.
                        // For now, let's assume we can calculate it or we store it in a RemoteKeys table.
                        (state.pages.size) + 1
                    }
                }
            }

            val response = receiptApi.getReceipts(
                page = page,
                pageSize = state.config.pageSize
            )

            database.withTransaction {
                if (loadType == LoadType.REFRESH) {
                    database.receiptDao().clearAll()
                }

                val entities = response.results.map { it.toEntity() }
                database.receiptDao().insertReceipts(entities)
            }

            MediatorResult.Success(
                endOfPaginationReached = response.next == null
            )
        } catch (e: Exception) {
            MediatorResult.Error(e)
        }
    }

    private fun io.eksoda.core.network.model.ReceiptResponse.toEntity(): ReceiptEntity {
        return ReceiptEntity(
            id = id,
            merchantId = merchant.id,
            merchantName = merchant.name,
            storeId = store?.id,
            storeName = store?.name,
            issuedAt = OffsetDateTime.parse(issued_at),
            totalAmount = BigDecimal(gross_total),
            currency = currency,
            url = source_url,
            createdAt = OffsetDateTime.parse(created_at)
        )
    }
}
