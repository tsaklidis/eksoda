package io.eksoda.core.network

import io.eksoda.core.network.api.AuthApi
import io.eksoda.core.network.model.RefreshRequest
import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import javax.inject.Inject
import javax.inject.Provider
import javax.inject.Singleton

@Singleton
class TokenAuthenticator @Inject constructor(
    private val tokenManager: TokenManager,
    private val authApiProvider: Provider<AuthApi>
) : Authenticator {

    override fun authenticate(route: Route?, response: Response): Request? {
        val refreshToken = runBlocking { tokenManager.getRefreshToken() } ?: return null

        synchronized(this) {
            val currentToken = runBlocking { tokenManager.getAccessToken() }
            val requestToken = response.request.header("Authorization")?.removePrefix("Bearer ")

            // If the token has already been updated by another thread, retry with the new token
            if (currentToken != null && currentToken != requestToken) {
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $currentToken")
                    .build()
            }

            return try {
                val refreshResponse = runBlocking {
                    authApiProvider.get().refresh(RefreshRequest(refreshToken))
                }

                runBlocking {
                    tokenManager.saveTokens(refreshResponse.access, refreshResponse.refresh)
                }

                response.request.newBuilder()
                    .header("Authorization", "Bearer ${refreshResponse.access}")
                    .build()
            } catch (e: Exception) {
                // Refresh failed, clear tokens to trigger logout
                runBlocking { tokenManager.clearTokens() }
                null
            }
        }
    }
}
