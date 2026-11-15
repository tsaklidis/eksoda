package io.eksoda.core.data.repository

import io.eksoda.core.model.Period
import io.eksoda.core.network.model.SummaryResponse
import io.eksoda.core.network.model.TrendResponse
import io.eksoda.core.network.model.CategorySpendingResponse
import kotlinx.coroutines.flow.Flow

interface AnalyticsRepository {
    suspend fun getSummary(period: Period): Result<SummaryResponse>
    suspend fun getMonthlyTrend(months: Int): Result<TrendResponse>
    suspend fun getSpendingByCategory(period: Period): Result<CategorySpendingResponse>
}
