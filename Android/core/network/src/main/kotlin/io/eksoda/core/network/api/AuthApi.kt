package io.eksoda.core.network.api

import io.eksoda.core.network.model.LoginRequest
import io.eksoda.core.network.model.PasswordLoginRequest
import io.eksoda.core.network.model.RefreshRequest
import io.eksoda.core.network.model.RegisterRequest
import io.eksoda.core.network.model.TokenResponse
import io.eksoda.core.network.model.UserResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {
    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body request: PasswordLoginRequest): TokenResponse

    @POST("auth/refresh")
    suspend fun refresh(@Body request: RefreshRequest): TokenResponse

    @POST("auth/logout")
    suspend fun logout(@Body request: RefreshRequest): Response<Unit>

    @GET("auth/me")
    suspend fun getCurrentUser(): UserResponse

    @POST("auth/password/change")
    suspend fun changePassword(@Body request: Map<String, String>): Response<Unit>
}
