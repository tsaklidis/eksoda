package io.eksoda.core.model

import java.time.OffsetDateTime

data class User(
    val id: String,
    val email: String,
    val displayName: String?,
    val createdAt: OffsetDateTime
)

data class Membership(
    val householdId: String,
    val householdName: String,
    val role: Role,
    val joinedAt: OffsetDateTime
)

enum class Role {
    OWNER,
    MEMBER;

    companion object {
        fun fromString(value: String): Role = when (value.lowercase()) {
            "owner" -> OWNER
            else -> MEMBER
        }
    }
}
