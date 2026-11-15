package io.eksoda.core.network.api

import io.eksoda.core.network.model.HouseholdResponse
import io.eksoda.core.network.model.JoinHouseholdRequest
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface HouseholdApi {
    @GET("households")
    suspend fun getHouseholds(): List<HouseholdResponse>

    @GET("households/{id}")
    suspend fun getHousehold(@Path("id") id: String): HouseholdResponse

    @POST("households/join")
    suspend fun joinHousehold(@Body request: JoinHouseholdRequest): HouseholdResponse
}
