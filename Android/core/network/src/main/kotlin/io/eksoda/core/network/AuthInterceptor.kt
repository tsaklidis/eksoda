package io.eksoda.core.network

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthInterceptor @Inject constructor(
    private val tokenManager: TokenManager
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val builder = request.newBuilder()

        // Skip auth for login/register/refresh if they are on specific paths
        val path = request.url.encodedPath
        val isAuthPath = path.contains("/auth/login") || 
                        path.contains("/auth/register") || 
                        path.contains("/auth/refresh")

        if (!isAuthPath) {
            val token = runBlocking { tokenManager.getAccessToken() }
            if (token != null) {
                builder.header("Authorization", "Bearer $token")
            }
        }

        return chain.proceed(builder.build())
    }
}
