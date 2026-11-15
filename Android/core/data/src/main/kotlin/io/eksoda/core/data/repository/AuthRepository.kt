package io.eksoda.core.data.repository

import io.eksoda.core.model.User
import kotlinx.coroutines.flow.Flow

interface AuthRepository {
    val currentUser: Flow<User?>
    val isAuthenticated: Flow<Boolean>

    suspend fun login(email: String, password: String): Result<Unit>
    suspend fun register(email: String, password: String, displayName: String?, inviteCode: String?): Result<Unit>
    suspend fun logout(): Result<Unit>
    suspend fun refreshUser(): Result<User>
}
