package io.eksoda.feature.receipts.detail

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.ReceiptRepository
import io.eksoda.core.model.Receipt
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ReceiptDetailViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val receiptId: String = checkNotNull(savedStateHandle["receiptId"])

    var uiState by mutableStateOf(ReceiptDetailUiState())
        private set

    init {
        loadReceipt()
    }

    fun loadReceipt() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            // Ideally we'd have a refreshReceipt method that fetches from network and updates cache
            // For now, let's assume we can get it or we add a specific fetch method
            receiptRepository.getReceipt(receiptId)
                .onEach { receipt ->
                    if (receipt != null) {
                        uiState = uiState.copy(isLoading = false, receipt = receipt)
                    }
                }
                .catch { e ->
                    uiState = uiState.copy(isLoading = false, error = e.message ?: "Failed to load receipt")
                }
                .collect()
        }
    }

    fun deleteReceipt() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true)
            val result = receiptRepository.deleteReceipt(receiptId)
            if (result.isSuccess) {
                uiState = uiState.copy(isLoading = false, isDeleted = true)
            } else {
                uiState = uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to delete receipt"
                )
            }
        }
    }
}

data class ReceiptDetailUiState(
    val receipt: Receipt? = null,
    val isLoading: Boolean = false,
    val isDeleted: Boolean = false,
    val error: String? = null
)
