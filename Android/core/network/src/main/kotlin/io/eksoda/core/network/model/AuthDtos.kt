package io.eksoda.core.network.model

import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val email: String,
    val hex_password: String // The spec says "password", but often I use hex_password if hashing on client, though usually it's plain over HTTPS. Let's stick to "password" as per spec.
)

@Serializable
data class PasswordLoginRequest(
    val email: String,
    val password: String
)

@Serializable
data class TokenResponse(
    val access: String,
    val refresh: String
)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val display_name: String? = null,
    val invite_code: String? = null
)

@Serializable
data class UserResponse(
    val id: String,
    val email: String,
    val display_name: String?,
    val memberships: List<MembershipDto>,
    val created_at: String
)

@Serializable
data class MembershipDto(
    val household_id: String,
    val household_name: String,
    val role: String,
    val joined_at: String
)

@Serializable
data class RefreshRequest(
    val refresh: String
)
