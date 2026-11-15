package io.eksoda.feature.scan.imports

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.HouseholdRepository
import io.eksoda.core.data.repository.ImportJob
import io.eksoda.core.data.repository.ReceiptRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ImportListViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    var uiState by mutableStateOf(ImportListUiState())
        private set

    private var isPolling = false

    init {
        loadImports()
        startPolling()
    }

    fun loadImports() {
        viewModelScope.launch {
            val household = householdRepository.selectedHousehold.filterNotNull().first()
            uiState = uiState.copy(isLoading = true, error = null)
            val result = receiptRepository.getImportJobs(household.id)
            uiState = if (result.isSuccess) {
                uiState.copy(isLoading = false, imports = result.getOrDefault(emptyList()))
            } else {
                uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to load imports"
                )
            }
        }
    }

    private fun startPolling() {
        if (isPolling) return
        isPolling = true
        viewModelScope.launch {
            while (isPolling) {
                delay(5000) // Poll every 5 seconds when visible
                val household = householdRepository.selectedHousehold.first()
                if (household != null) {
                    val result = receiptRepository.getImportJobs(household.id)
                    if (result.isSuccess) {
                        uiState = uiState.copy(imports = result.getOrDefault(emptyList()))
                    }
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        isPolling = false
    }

    fun retryImport(id: String) {
        viewModelScope.launch {
            receiptRepository.retryImport(id)
            loadImports()
        }
    }
}

data class ImportListUiState(
    val imports: List<ImportJob> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null
)
