package io.eksoda

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.AuthRepository
import io.eksoda.core.data.repository.HouseholdRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MainViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val householdRepository: HouseholdRepository
) : ViewModel() {

    private val _sharedUrl = MutableStateFlow<String?>(null)
    val sharedUrl: StateFlow<String?> = _sharedUrl.asStateFlow()

    val uiState: StateFlow<MainUiState> = combine(
        authRepository.isAuthenticated,
        authRepository.currentUser,
        householdRepository.selectedHousehold
    ) { isAuthenticated, user, household ->
        when {
            !isAuthenticated -> MainUiState.Unauthenticated
            user == null -> MainUiState.Loading
            household == null -> MainUiState.HouseholdSelectionRequired
            else -> MainUiState.Authenticated
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = MainUiState.Loading
    )

    init {
        viewModelScope.launch {
            authRepository.isAuthenticated.collect { authenticated ->
                if (authenticated) {
                    authRepository.refreshUser()
                    householdRepository.refreshSelectedHousehold()
                }
            }
        }
    }

    fun onSharedUrlReceived(url: String) {
        _sharedUrl.value = url
    }

    fun onSharedUrlHandled() {
        _sharedUrl.value = null
    }
}

sealed interface MainUiState {
    data object Loading : MainUiState
    data object Unauthenticated : MainUiState
    data object Authenticated : MainUiState
    data object HouseholdSelectionRequired : MainUiState
}
