package io.eksoda.core.data.repository

import io.eksoda.core.model.Period
import io.eksoda.core.network.api.AnalyticsApi
import io.eksoda.core.network.model.CategorySpendingResponse
import io.eksoda.core.network.model.SummaryResponse
import io.eksoda.core.network.model.TrendResponse
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AnalyticsRepositoryImpl @Inject constructor(
    private val analyticsApi: AnalyticsApi
) : AnalyticsRepository {

    private val dateFormatter = DateTimeFormatter.ISO_LOCAL_DATE

    override suspend fun getSummary(period: Period): Result<SummaryResponse> {
        return try {
            val response = analyticsApi.getSummary(
                from = period.start.format(dateFormatter),
                to = period.end.format(dateFormatter)
            )
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getMonthlyTrend(months: Int): Result<TrendResponse> {
        return try {
            val response = analyticsApi.getMonthlyTrend(months = months)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getSpendingByCategory(period: Period): Result<CategorySpendingResponse> {
        return try {
            val response = analyticsApi.getSpendingByCategory(
                from = period.start.format(dateFormatter),
                to = period.end.format(dateFormatter)
            )
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
