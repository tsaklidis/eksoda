package io.eksoda.core.network.model

import kotlinx.serialization.Serializable

@Serializable
data class ProductResponse(
    val id: String,
    val name: String,
    val category: CategoryDto?,
    val brand: String? = null,
    val unit: String? = null,
    val last_price: String? = null,
    val last_price_at: String? = null,
    val is_reviewed: Boolean,
    val line_count: Int? = null,
    val package_quantity: Double? = null,
    val package_unit: String? = null
)

@Serializable
data class ProductPriceResponse(
    val id: String,
    val receipt_id: String,
    val issued_at: String,
    val merchant_name: String,
    val quantity: Double,
    val unit: String?,
    val unit_price: String,
    val total_price: String,
    val normalized_unit_price: String?,
    val normalized_unit: String?
)

@Serializable
data class ProductPriceStatsResponse(
    val stats: List<PriceStatDto>,
    val available_units: List<String>
)

@Serializable
data class PriceStatDto(
    val currency: String,
    val unit: String,
    val latest: String,
    val minimum: String,
    val maximum: String,
    val average: String,
    val count: Int
)

@Serializable
data class PriceComparisonResponse(
    val comparable: Boolean,
    val reason: String? = null,
    val currency: String? = null,
    val unit: String? = null,
    val merchants: List<MerchantPriceComparisonDto> = emptyList()
)

@Serializable
data class MerchantPriceComparisonDto(
    val merchant_id: String,
    val merchant_name: String,
    val average_price: String,
    val min_price: String,
    val max_price: String,
    val rank: Int
)

@Serializable
data class CreateProductRequest(
    val name: String,
    val category_id: String? = null,
    val brand: String? = null,
    val package_quantity: Double? = null,
    val package_unit: String? = null
)

@Serializable
data class MergeProductsRequest(
    val source_product_ids: List<String>
)

@Serializable
data class ReviewItemResponse(
    val id: String,
    val receipt_id: String,
    val merchant_name: String,
    val issued_at: String,
    val description: String,
    val quantity: Double?,
    val unit: String?,
    val gross_amount: String,
    val currency: String,
    val merchant_product_code: String?
)
