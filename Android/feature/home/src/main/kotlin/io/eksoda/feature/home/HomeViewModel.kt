package io.eksoda.feature.home

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.AnalyticsRepository
import io.eksoda.core.data.repository.HouseholdRepository
import io.eksoda.core.model.Period
import io.eksoda.core.network.model.SummaryResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val analyticsRepository: AnalyticsRepository,
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    var uiState by mutableStateOf(HomeUiState())
        private set

    init {
        loadDashboard()
    }

    fun loadDashboard() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val household = householdRepository.selectedHousehold.filterNotNull().first()
            
            val result = analyticsRepository.getSummary(Period.current())
            uiState = if (result.isSuccess) {
                uiState.copy(
                    isLoading = false,
                    summary = result.getOrNull(),
                    householdName = household.name
                )
            } else {
                uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to load dashboard"
                )
            }
        }
    }
}

data class HomeUiState(
    val summary: SummaryResponse? = null,
    val householdName: String = "",
    val isLoading: Boolean = false,
    val error: String? = null
)
