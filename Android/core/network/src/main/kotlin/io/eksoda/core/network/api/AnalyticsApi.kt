package io.eksoda.core.network.api

import io.eksoda.core.network.model.CategorySpendingResponse
import io.eksoda.core.network.model.MerchantSpendingResponse
import io.eksoda.core.network.model.SummaryResponse
import io.eksoda.core.network.model.TopProductsResponse
import io.eksoda.core.network.model.TrendResponse
import retrofit2.http.GET
import retrofit2.http.Query

interface AnalyticsApi {
    @GET("analytics/summary")
    suspend fun getSummary(
        @Query("from") from: String? = null,
        @Query("to") to: String? = null
    ): SummaryResponse

    @GET("analytics/spending-by-category")
    suspend fun getSpendingByCategory(
        @Query("from") from: String? = null,
        @Query("to") to: String? = null
    ): CategorySpendingResponse

    @GET("analytics/spending-by-merchant")
    suspend fun getSpendingByMerchant(
        @Query("from") from: String? = null,
        @Query("to") to: String? = null
    ): MerchantSpendingResponse

    @GET("analytics/monthly-trend")
    suspend fun getMonthlyTrend(
        @Query("to") to: String? = null,
        @Query("months") months: Int? = null
    ): TrendResponse

    @GET("analytics/top-products")
    suspend fun getTopProducts(
        @Query("from") from: String? = null,
        @Query("to") to: String? = null,
        @Query("by") by: String? = null, // "count" or "spend"
        @Query("limit") limit: Int? = null
    ): TopProductsResponse
}
