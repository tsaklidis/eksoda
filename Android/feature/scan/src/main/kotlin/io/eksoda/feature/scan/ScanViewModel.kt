package io.eksoda.feature.scan

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.HouseholdRepository
import io.eksoda.core.data.repository.ReceiptRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ScanViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    var uiState by mutableStateOf(ScanUiState())
        private set

    fun onQrScanned(url: String) {
        if (uiState.isSubmitting || url == uiState.lastScannedUrl) return

        viewModelScope.launch {
            val household = householdRepository.selectedHousehold.first()
            if (household == null) {
                uiState = uiState.copy(error = "No household selected")
                return@launch
            }

            uiState = uiState.copy(isSubmitting = true, lastScannedUrl = url, error = null)
            val result = receiptRepository.importReceipt(url, household.id)
            
            uiState = if (result.isSuccess) {
                uiState.copy(
                    isSubmitting = false,
                    successMessage = "Receipt submitted successfully"
                )
            } else {
                uiState.copy(
                    isSubmitting = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to submit receipt"
                )
            }
        }
    }

    fun clearMessages() {
        uiState = uiState.copy(error = null, successMessage = null)
    }

    fun onUrlPasted(url: String) {
        onQrScanned(url)
    }
}

data class ScanUiState(
    val isSubmitting: Boolean = false,
    val lastScannedUrl: String? = null,
    val error: String? = null,
    val successMessage: String? = null
)
