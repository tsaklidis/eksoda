package io.eksoda.core.network.api

import io.eksoda.core.network.model.ImportJobResponse
import io.eksoda.core.network.model.ReceiptImportRequest
import io.eksoda.core.network.model.ReceiptResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ReceiptApi {
    @POST("receipts/import")
    suspend fun importReceipt(@Body request: ReceiptImportRequest): ImportJobResponse

    @GET("receipts")
    suspend fun getReceipts(
        @Query("page") page: Int? = null,
        @Query("page_size") pageSize: Int? = null,
        @Query("ordering") ordering: String? = null,
        @Query("merchant") merchantId: String? = null,
        @Query("issued_from") issuedFrom: String? = null,
        @Query("issued_to") issuedTo: String? = null
    ): PagedResponse<ReceiptResponse>

    @GET("receipts/{id}")
    suspend fun getReceipt(@Path("id") id: String): ReceiptResponse

    @PATCH("receipts/{id}")
    suspend fun updateReceipt(@Path("id") id: String, @Body fields: Map<String, String>): ReceiptResponse

    @DELETE("receipts/{id}")
    suspend fun deleteReceipt(@Path("id") id: String): Response<Unit>

    @GET("receipt-imports")
    suspend fun getImportJobs(): List<ImportJobResponse>

    @GET("receipt-imports/{id}")
    suspend fun getImportJob(@Path("id") id: String): ImportJobResponse

    @POST("receipt-imports/{id}/retry")
    suspend fun retryImport(@Path("id") id: String): Response<Unit>
}

@kotlinx.serialization.Serializable
data class PagedResponse<T>(
    val count: Int,
    val next: String?,
    val previous: String?,
    val results: List<T>
)
