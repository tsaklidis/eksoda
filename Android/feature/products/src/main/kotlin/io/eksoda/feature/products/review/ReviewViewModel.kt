package io.eksoda.feature.products.review

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import io.eksoda.core.data.repository.ProductRepository
import io.eksoda.core.network.model.ReviewItemResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ReviewViewModel @Inject constructor(
    private val productRepository: ProductRepository
) : ViewModel() {

    val items: Flow<PagingData<ReviewItemResponse>> = productRepository.getReviewItems()
        .cachedIn(viewModelScope)

    var uiState by mutableStateOf(ReviewUiState())
        private set

    fun matchToProduct(itemId: String, productId: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isSubmitting = true)
            val result = productRepository.matchItem(itemId, productId)
            uiState = if (result.isSuccess) {
                uiState.copy(isSubmitting = false, successMessage = "Item matched successfully")
            } else {
                uiState.copy(
                    isSubmitting = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to match item"
                )
            }
        }
    }

    fun createProduct(itemId: String, name: String, categoryId: String?) {
        viewModelScope.launch {
            uiState = uiState.copy(isSubmitting = true)
            val result = productRepository.createProductFromItem(itemId, name, categoryId)
            uiState = if (result.isSuccess) {
                uiState.copy(isSubmitting = false, successMessage = "Product created and matched")
            } else {
                uiState.copy(
                    isSubmitting = false,
                    error = result.exceptionOrNull()?.message ?: "Failed to create product"
                )
            }
        }
    }

    fun clearMessages() {
        uiState = uiState.copy(error = null, successMessage = null)
    }
}

data class ReviewUiState(
    val isSubmitting: Boolean = false,
    val error: String? = null,
    val successMessage: String? = null
)
