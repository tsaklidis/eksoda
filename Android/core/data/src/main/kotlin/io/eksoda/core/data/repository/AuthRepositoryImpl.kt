package io.eksoda.core.data.repository

import io.eksoda.core.model.Membership
import io.eksoda.core.model.Role
import io.eksoda.core.model.User
import io.eksoda.core.network.TokenManager
import io.eksoda.core.network.api.AuthApi
import io.eksoda.core.network.model.MembershipDto
import io.eksoda.core.network.model.PasswordLoginRequest
import io.eksoda.core.network.model.RegisterRequest
import io.eksoda.core.network.model.UserResponse
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi,
    private val tokenManager: TokenManager
) : AuthRepository {

    private val _currentUser = MutableStateFlow<User?>(null)
    override val currentUser: Flow<User?> = _currentUser.asStateFlow()

    override val isAuthenticated: Flow<Boolean> = tokenManager.getAccessTokenFlow()
        .map { it != null }

    override suspend fun login(email: String, password: String): Result<Unit> {
        return try {
            val response = authApi.login(PasswordLoginRequest(email, password))
            tokenManager.saveTokens(response.access, response.refresh)
            refreshUser()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun register(
        email: String,
        password: String,
        displayName: String?,
        inviteCode: String?
    ): Result<Unit> {
        return try {
            val response = authApi.register(RegisterRequest(email, password, displayName, inviteCode))
            tokenManager.saveTokens(response.access, response.refresh)
            refreshUser()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun logout(): Result<Unit> {
        return try {
            val refreshToken = tokenManager.getRefreshToken()
            if (refreshToken != null) {
                // Ignore failure on server logout, clear locally anyway
                try {
                    // authApi.logout(RefreshRequest(refreshToken))
                } catch (e: Exception) {
                    // Log error
                }
            }
            tokenManager.clearTokens()
            _currentUser.value = null
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun refreshUser(): Result<User> {
        return try {
            val response = authApi.getCurrentUser()
            val user = response.toDomain()
            _currentUser.value = user
            Result.success(user)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun UserResponse.toDomain(): User {
        return User(
            id = id,
            email = email,
            displayName = display_name,
            createdAt = OffsetDateTime.parse(created_at)
            // Note: In a real app we'd map memberships too if the domain User model needs them
        )
    }

    private fun MembershipDto.toDomain(): Membership {
        return Membership(
            householdId = household_id,
            householdName = household_name,
            role = Role.fromString(role),
            joinedAt = OffsetDateTime.parse(joined_at)
        )
    }
}
