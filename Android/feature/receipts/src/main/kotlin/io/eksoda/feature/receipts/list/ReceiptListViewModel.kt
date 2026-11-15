package io.eksoda.feature.receipts.list

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import io.eksoda.core.data.repository.HouseholdRepository
import io.eksoda.core.data.repository.ReceiptRepository
import io.eksoda.core.model.Receipt
import io.eksoda.core.model.ReceiptFilter
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import javax.inject.Inject

@HiltViewModel
class ReceiptListViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    var filter by mutableStateOf(ReceiptFilter())
        private set

    @OptIn(ExperimentalCoroutinesApi::class)
    val receipts: Flow<PagingData<Receipt>> = householdRepository.selectedHousehold
        .filterNotNull()
        .flatMapLatest { household ->
            receiptRepository.getReceipts(household.id)
        }
        .cachedIn(viewModelScope)

    fun onQueryChange(query: String) {
        filter = filter.copy(query = query)
        // In a real app, this would trigger a new search/filter
    }

    fun onFilterChange(newFilter: ReceiptFilter) {
        filter = newFilter
    }
}
