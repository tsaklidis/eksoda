package io.eksoda.core.data.repository

import androidx.paging.PagingData
import io.eksoda.core.model.Product
import io.eksoda.core.network.model.PriceComparisonResponse
import io.eksoda.core.network.model.ProductPriceResponse
import io.eksoda.core.network.model.ReviewItemResponse
import kotlinx.coroutines.flow.Flow

interface ProductRepository {
    fun getProducts(query: String? = null, categoryId: String? = null): Flow<PagingData<Product>>
    suspend fun getProduct(id: String): Result<Product>
    suspend fun getProductPrices(id: String, unit: String? = null): Result<List<ProductPriceResponse>>
    suspend fun getPriceComparison(id: String, unit: String? = null): Result<PriceComparisonResponse>
    
    suspend fun getReviewItems(): Flow<PagingData<ReviewItemResponse>>
    suspend fun matchItem(itemId: String, productId: String): Result<Unit>
    suspend fun createProductFromItem(itemId: String, name: String, categoryId: String?): Result<Product>
}
