package io.eksoda.core.network.api

import io.eksoda.core.network.model.CreateProductRequest
import io.eksoda.core.network.model.MergeProductsRequest
import io.eksoda.core.network.model.PagedResponse
import io.eksoda.core.network.model.PriceComparisonResponse
import io.eksoda.core.network.model.ProductPriceResponse
import io.eksoda.core.network.model.ProductPriceStatsResponse
import io.eksoda.core.network.model.ProductResponse
import io.eksoda.core.network.model.ReviewItemResponse
import retrofit2.Response
import retrofit2.http.*

interface ProductApi {
    @GET("products")
    suspend fun getProducts(
        @Query("page") page: Int? = null,
        @Query("q") query: String? = null,
        @Query("category") categoryId: String? = null,
        @Query("brand") brand: String? = null,
        @Query("merchant") merchantId: String? = null,
        @Query("ordering") ordering: String? = null
    ): PagedResponse<ProductResponse>

    @POST("products")
    suspend fun createProduct(@Body request: CreateProductRequest): ProductResponse

    @GET("products/{id}")
    suspend fun getProduct(@Path("id") id: String): ProductResponse

    @PATCH("products/{id}")
    suspend fun updateProduct(@Path("id") id: String, @Body fields: Map<String, String>): ProductResponse

    @GET("products/{id}/prices")
    suspend fun getProductPrices(
        @Path("id") id: String,
        @Query("page") page: Int? = null,
        @Query("normalized_unit") unit: String? = null
    ): PagedResponse<ProductPriceResponse>

    @GET("products/{id}/price-comparison")
    suspend fun getProductPriceComparison(
        @Path("id") id: String,
        @Query("normalized_unit") unit: String? = null
    ): PriceComparisonResponse

    @POST("products/{id}/merge")
    suspend fun mergeProducts(@Path("id") id: String, @Body request: MergeProductsRequest): Response<Unit>

    @GET("receipt-items/review")
    suspend fun getReviewItems(@Query("page") page: Int? = null): PagedResponse<ReviewItemResponse>

    @POST("receipt-items/{id}/match")
    suspend fun matchItem(@Path("id") id: String, @Body request: Map<String, String>): Response<Unit>

    @POST("receipt-items/{id}/create-product")
    suspend fun createProductFromItem(@Path("id") id: String, @Body request: CreateProductRequest): ProductResponse
}
