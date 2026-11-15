package io.eksoda.core.data.repository

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.map
import io.eksoda.core.model.Category
import io.eksoda.core.model.Money
import io.eksoda.core.model.Product
import io.eksoda.core.network.api.ProductApi
import io.eksoda.core.network.model.CreateProductRequest
import io.eksoda.core.network.model.PriceComparisonResponse
import io.eksoda.core.network.model.ProductPriceResponse
import io.eksoda.core.network.model.ReviewItemResponse
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.math.BigDecimal
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ProductRepositoryImpl @Inject constructor(
    private val productApi: ProductApi
) : ProductRepository {

    override fun getProducts(query: String?, categoryId: String?): Flow<PagingData<Product>> {
        return Pager(
            config = PagingConfig(pageSize = 25),
            pagingSourceFactory = { 
                // Using a simple PagingSource implementation or a generated one.
                // For now, let's assume we have a way to fetch pages from the API.
                // In a full implementation, we'd use a generic PagingSource or a RemoteMediator.
                ProductPagingSource(productApi, query, categoryId)
            }
        ).flow.map { pagingData ->
            pagingData.map { it.toDomain() }
        }
    }

    override suspend fun getProduct(id: String): Result<Product> {
        return try {
            val response = productApi.getProduct(id)
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getProductPrices(id: String, unit: String?): Result<List<ProductPriceResponse>> {
        return try {
            val response = productApi.getProductPrices(id, unit = unit)
            Result.success(response.results)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getPriceComparison(id: String, unit: String?): Result<PriceComparisonResponse> {
        return try {
            val response = productApi.getProductPriceComparison(id, unit = unit)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override fun getReviewItems(): Flow<PagingData<ReviewItemResponse>> {
        return Pager(
            config = PagingConfig(pageSize = 25),
            pagingSourceFactory = { ReviewPagingSource(productApi) }
        ).flow
    }

    override suspend fun matchItem(itemId: String, productId: String): Result<Unit> {
        return try {
            productApi.matchItem(itemId, mapOf("product_id" to productId))
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun createProductFromItem(
        itemId: String,
        name: String,
        categoryId: String?
    ): Result<Product> {
        return try {
            val response = productApi.createProductFromItem(
                itemId,
                CreateProductRequest(name = name, category_id = categoryId)
            )
            Result.success(response.toDomain())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun io.eksoda.core.network.model.ProductResponse.toDomain(): Product {
        return Product(
            id = id,
            name = name,
            category = category?.let { 
                Category(it.id, it.name, it.icon, it.color, it.is_system)
            },
            brand = brand,
            unit = unit,
            lastPrice = last_price?.let { Money(BigDecimal(it), "") }, // Currency missing in summary?
            lastPriceAt = last_price_at?.let { OffsetDateTime.parse(it) },
            isReviewed = is_reviewed
        )
    }
}

// Temporary internal classes for PagingSource
private class ProductPagingSource(
    private val api: ProductApi,
    private val query: String?,
    private val categoryId: String?
) : androidx.paging.PagingSource<Int, io.eksoda.core.network.model.ProductResponse>() {
    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, io.eksoda.core.network.model.ProductResponse> {
        val page = params.key ?: 1
        return try {
            val response = api.getProducts(page = page, query = query, categoryId = categoryId)
            LoadResult.Page(
                data = response.results,
                prevKey = if (page == 1) null else page - 1,
                nextKey = if (response.next == null) null else page + 1
            )
        } catch (e: Exception) {
            LoadResult.Error(e)
        }
    }
    override fun getRefreshKey(state: androidx.paging.PagingState<Int, io.eksoda.core.network.model.ProductResponse>): Int? = null
}

private class ReviewPagingSource(
    private val api: ProductApi
) : androidx.paging.PagingSource<Int, ReviewItemResponse>() {
    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, ReviewItemResponse> {
        val page = params.key ?: 1
        return try {
            val response = api.getReviewItems(page = page)
            LoadResult.Page(
                data = response.results,
                prevKey = if (page == 1) null else page - 1,
                nextKey = if (response.next == null) null else page + 1
            )
        } catch (e: Exception) {
            LoadResult.Error(e)
        }
    }
    override fun getRefreshKey(state: androidx.paging.PagingState<Int, ReviewItemResponse>): Int? = null
}
