package io.eksoda.feature.insights

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.AnalyticsRepository
import io.eksoda.core.model.Period
import io.eksoda.core.network.model.CategorySpendingResponse
import io.eksoda.core.network.model.SummaryResponse
import io.eksoda.core.network.model.TrendResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class InsightsViewModel @Inject constructor(
    private val analyticsRepository: AnalyticsRepository
) : ViewModel() {

    var uiState by mutableStateOf(InsightsUiState())
        private set

    init {
        loadInsights()
    }

    fun onPeriodChange(period: Period) {
        uiState = uiState.copy(selectedPeriod = period)
        loadInsights()
    }

    fun loadInsights() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val period = uiState.selectedPeriod

            val summaryDeferred = async { analyticsRepository.getSummary(period) }
            val categoriesDeferred = async { analyticsRepository.getSpendingByCategory(period) }
            val trendDeferred = async { analyticsRepository.getMonthlyTrend(12) }

            val summaryResult = summaryDeferred.await()
            val categoriesResult = categoriesDeferred.await()
            val trendResult = trendDeferred.await()

            if (summaryResult.isSuccess && categoriesResult.isSuccess && trendResult.isSuccess) {
                uiState = uiState.copy(
                    isLoading = false,
                    summary = summaryResult.getOrNull(),
                    categorySpending = categoriesResult.getOrNull(),
                    trend = trendResult.getOrNull()
                )
            } else {
                uiState = uiState.copy(
                    isLoading = false,
                    error = "Failed to load some insight data"
                )
            }
        }
    }
}

data class InsightsUiState(
    val selectedPeriod: Period = Period.current(),
    val summary: SummaryResponse? = null,
    val categorySpending: CategorySpendingResponse? = null,
    val trend: TrendResponse? = null,
    val isLoading: Boolean = false,
    val error: String? = null
)
