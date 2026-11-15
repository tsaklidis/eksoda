package io.eksoda.core.network.model

import kotlinx.serialization.Serializable

@Serializable
data class ReceiptResponse(
    val id: String,
    val merchant: MerchantDto,
    val store: StoreDto?,
    val issued_at: String,
    val currency: String,
    val gross_total: String,
    val net_total: String?,
    val vat_total: String?,
    val discount_total: String?,
    val payment_method: String,
    val status: String,
    val user_note: String,
    val excluded_from_analytics: Boolean,
    val source_url: String? = null,
    val items: List<ReceiptItemResponse>? = null,
    val created_at: String,
    val needs_review: Boolean? = null
)

@Serializable
data class MerchantDto(
    val id: String,
    val display_name: String,
    val vat_number: String? = null,
    val website: String? = null
)

@Serializable
data class StoreDto(
    val id: String,
    val name: String,
    val address: String? = null,
    val city: String? = null,
    val street: String? = null,
    val postal_code: String? = null
)

@Serializable
data class ReceiptItemResponse(
    val id: String,
    val line_number: Int,
    val line_type: String,
    val description: String,
    val quantity: Double?,
    val unit: String?,
    val unit_price: String?,
    val gross_amount: String,
    val product: ProductDto?,
    val match_status: String,
    val user_note: String? = null
)

@Serializable
data class ProductDto(
    val id: String,
    val name: String,
    val category: CategoryDto?,
    val brand: String? = null,
    val unit: String? = null,
    val last_price: String? = null,
    val last_price_at: String? = null,
    val is_reviewed: Boolean
)

@Serializable
data class CategoryDto(
    val id: String,
    val name: String,
    val icon: String?,
    val color: String?,
    val is_system: Boolean
)

@Serializable
data class ReceiptImportRequest(
    val url: String
)

@Serializable
data class ImportJobResponse(
    val id: String,
    val status: String,
    val outcome: String?,
    val provider_code: String,
    val submitted_url: String,
    val created_at: String,
    val finished_at: String?,
    val receipt_id: String?,
    val error: ImportErrorDto?
)

@Serializable
data class ImportErrorDto(
    val code: String,
    val message: String
)
