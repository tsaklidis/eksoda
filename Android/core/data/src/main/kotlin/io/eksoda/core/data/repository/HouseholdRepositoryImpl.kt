package io.eksoda.core.data.repository

import io.eksoda.core.model.Invitation
import io.eksoda.core.model.Role
import io.eksoda.core.network.api.AuthApi
import io.eksoda.core.network.api.HouseholdApi
import io.eksoda.core.network.model.JoinHouseholdRequest
import kotlinx.coroutines.flow.*
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HouseholdRepositoryImpl @Inject constructor(
    private val householdApi: HouseholdApi,
    private val authApi: AuthApi,
    private val userPreferences: UserPreferencesRepository
) : HouseholdRepository {

    private val _selectedHousehold = MutableStateFlow<HouseholdInfo?>(null)
    override val selectedHousehold: Flow<HouseholdInfo?> = _selectedHousehold.asStateFlow()

    override suspend fun getHouseholds(): Result<List<HouseholdInfo>> {
        return try {
            val response = householdApi.getHouseholds()
            val list = response.map {
                HouseholdInfo(
                    id = it.id,
                    name = it.name,
                    role = Role.MEMBER, // Default until we fetch from /auth/me
                    defaultCurrency = it.default_currency,
                    timezone = it.timezone
                )
            }
            Result.success(list)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun selectHousehold(id: String): Result<Unit> {
        return try {
            userPreferences.setHouseholdId(id)
            refreshSelectedHousehold()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun joinHousehold(inviteCode: String): Result<HouseholdInfo> {
        return try {
            val response = householdApi.joinHousehold(JoinHouseholdRequest(inviteCode))
            val info = HouseholdInfo(
                id = response.id,
                name = response.name,
                role = Role.MEMBER,
                defaultCurrency = response.default_currency,
                timezone = response.timezone
            )
            selectHousehold(info.id)
            Result.success(info)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun refreshSelectedHousehold(): Result<Unit> {
        return try {
            val id = userPreferences.getSelectedHouseholdId()
            if (id != null) {
                // Fetch details and also check role from /auth/me
                val userResponse = authApi.getCurrentUser()
                val membership = userResponse.memberships.find { it.household_id == id }
                
                val response = householdApi.getHousehold(id)
                _selectedHousehold.value = HouseholdInfo(
                    id = response.id,
                    name = response.name,
                    role = membership?.role?.let { Role.fromString(it) } ?: Role.MEMBER,
                    defaultCurrency = response.default_currency,
                    timezone = response.timezone
                )
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun updateHousehold(
        id: String,
        name: String,
        currency: String,
        timezone: String
    ): Result<Unit> {
        return try {
            // householdApi.updateHousehold(id, mapOf("name" to name, ...))
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getMembers(id: String): Result<List<Member>> {
        return try {
            // val response = householdApi.getMembers(id)
            Result.success(emptyList())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun removeMember(householdId: String, memberId: String): Result<Unit> {
        return try {
            // householdApi.removeMember(householdId, memberId)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getInvitations(id: String): Result<List<Invitation>> {
        return try {
            // val response = householdApi.getInvitations(id)
            Result.success(emptyList())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun createInvitation(id: String, role: Role): Result<Invitation> {
        return try {
            // val response = householdApi.createInvitation(id, role.name.lowercase())
            Result.failure(Exception("Not implemented"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun revokeInvitation(householdId: String, invitationId: String): Result<Unit> {
        return try {
            // householdApi.revokeInvitation(householdId, invitationId)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
