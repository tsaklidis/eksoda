package io.eksoda.feature.auth.register

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.eksoda.core.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class RegisterViewModel @Inject constructor(
    private val authRepository: AuthRepository
) : ViewModel() {

    var uiState by mutableStateOf(RegisterUiState())
        private set

    fun onEmailChange(email: String) {
        uiState = uiState.copy(email = email, error = null)
    }

    fun onPasswordChange(password: String) {
        uiState = uiState.copy(password = password, error = null)
    }

    fun onDisplayNameChange(displayName: String) {
        uiState = uiState.copy(displayName = displayName, error = null)
    }

    fun onInviteCodeChange(inviteCode: String) {
        uiState = uiState.copy(inviteCode = inviteCode, error = null)
    }

    fun register() {
        if (uiState.email.isBlank() || uiState.password.isBlank()) {
            uiState = uiState.copy(error = "Email and password are required")
            return
        }

        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            val result = authRepository.register(
                email = uiState.email,
                password = uiState.password,
                displayName = uiState.displayName.takeIf { it.isNotBlank() },
                inviteCode = uiState.inviteCode.takeIf { it.isNotBlank() }
            )
            uiState = if (result.isSuccess) {
                uiState.copy(isLoading = false, isSuccess = true)
            } else {
                uiState.copy(
                    isLoading = false,
                    error = result.exceptionOrNull()?.message ?: "Registration failed"
                )
            }
        }
    }
}

data class RegisterUiState(
    val email: String = "",
    val password: String = "",
    val displayName: String = "",
    val inviteCode: String = "",
    val isLoading: Boolean = false,
    val isSuccess: Boolean = false,
    val error: String? = null
)
