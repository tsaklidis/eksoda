package io.eksoda.core.data.repository

import io.eksoda.core.model.Role
import io.eksoda.core.model.Invitation
import kotlinx.coroutines.flow.Flow

data class HouseholdInfo(
    val id: String,
    val name: String,
    val role: Role,
    val defaultCurrency: String,
    val timezone: String
)

data class Member(
    val id: String,
    val userId: String,
    val email: String,
    val displayName: String?,
    val role: Role,
    val joinedAt: java.time.OffsetDateTime
)

interface HouseholdRepository {
    val selectedHousehold: Flow<HouseholdInfo?>
    
    suspend fun getHouseholds(): Result<List<HouseholdInfo>>
    suspend fun selectHousehold(id: String): Result<Unit>
    suspend fun joinHousehold(inviteCode: String): Result<HouseholdInfo>
    suspend fun refreshSelectedHousehold(): Result<Unit>
    
    suspend fun updateHousehold(id: String, name: String, currency: String, timezone: String): Result<Unit>
    suspend fun getMembers(id: String): Result<List<Member>>
    suspend fun removeMember(householdId: String, memberId: String): Result<Unit>
    
    suspend fun getInvitations(id: String): Result<List<Invitation>>
    suspend fun createInvitation(id: String, role: Role): Result<Invitation>
    suspend fun revokeInvitation(householdId: String, invitationId: String): Result<Unit>
}
