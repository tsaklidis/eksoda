package io.eksoda.feature.products.detail

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.ProductRepository
import io.eksoda.core.model.Product
import io.eksoda.core.network.model.PriceComparisonResponse
import io.eksoda.core.network.model.ProductPriceResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProductDetailViewModel @Inject constructor(
    private val productRepository: ProductRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val productId: String = checkNotNull(savedStateHandle["productId"])

    var uiState by mutableStateOf(ProductDetailUiState())
        private set

    init {
        loadProductData()
    }

    fun loadProductData() {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            
            val productDeferred = async { productRepository.getProduct(productId) }
            val pricesDeferred = async { productRepository.getProductPrices(productId, uiState.selectedUnit) }
            val comparisonDeferred = async { productRepository.getPriceComparison(productId, uiState.selectedUnit) }

            val productResult = productDeferred.await()
            val pricesResult = pricesDeferred.await()
            val comparisonResult = comparisonDeferred.await()

            if (productResult.isSuccess) {
                uiState = uiState.copy(
                    isLoading = false,
                    product = productResult.getOrNull(),
                    prices = pricesResult.getOrDefault(emptyList()),
                    comparison = comparisonResult.getOrNull()
                )
            } else {
                uiState = uiState.copy(
                    isLoading = false,
                    error = productResult.exceptionOrNull()?.message ?: "Failed to load product"
                )
            }
        }
    }

    fun onUnitChange(unit: String) {
        uiState = uiState.copy(selectedUnit = unit)
        loadProductData()
    }
}

data class ProductDetailUiState(
    val product: Product? = null,
    val prices: List<ProductPriceResponse> = emptyList(),
    val comparison: PriceComparisonResponse? = null,
    val selectedUnit: String? = null,
    val isLoading: Boolean = false,
    val error: String? = null
)
