package io.eksoda.core.network.model

import kotlinx.serialization.Serializable

@Serializable
data class HouseholdResponse(
    val id: String,
    val name: String,
    val default_currency: String,
    val timezone: String,
    val created_at: String
)

@Serializable
data class JoinHouseholdRequest(
    val invite_code: String
)
