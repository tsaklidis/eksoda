package io.eksoda.feature.household.picker

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.HouseholdInfo
import io.eksoda.core.data.repository.HouseholdRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HouseholdPickerViewModel @Inject constructor(
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    var uiState by mutableStateOf(HouseholdPickerUiState())
        private set

    init {
        loadHouseholds()
    }

    fun loadHouseholds() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val result = householdRepository.getHouseholds()
            uiState = if (result.isSuccess) {
                uiState.copy(isLoading = false, households = result.getOrDefault(emptyList()))
            } else {
                uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to load households"
                )
            }
        }
    }

    fun selectHousehold(id: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true)
            val result = householdRepository.selectHousehold(id)
            if (result.isFailure) {
                uiState = uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to select household"
                )
            }
            // If success, the MainViewModel will observe the change and navigate
        }
    }

    fun joinHousehold(inviteCode: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val result = householdRepository.joinHousehold(inviteCode)
            if (result.isFailure) {
                uiState = uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to join household"
                )
            }
        }
    }
}

data class HouseholdPickerUiState(
    val households: List<HouseholdInfo> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null
)
