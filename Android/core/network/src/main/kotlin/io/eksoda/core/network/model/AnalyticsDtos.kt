package io.eksoda.core.network.model

import kotlinx.serialization.Serializable

@Serializable
data class SummaryResponse(
    val currency: String,
    val current: TotalsDto,
    val previous: PreviousDto,
    val change_amount: String,
    val change_percent: Double?,
    val needs_review_count: Int
)

@Serializable
data class TotalsDto(
    val period: PeriodDto,
    val spending: String,
    val receipt_count: Int,
    val sales_count: Int,
    val average_sale: String?,
    val credit_notes_total: String,
    val other_currency_receipts: Int
)

@Serializable
data class PreviousDto(
    val period: PeriodDto,
    val spending: String
)

@Serializable
data class PeriodDto(
    val from: String,
    val to: String
)

@Serializable
data class CategorySpendingResponse(
    val period: PeriodDto,
    val currency: String,
    val total: String,
    val buckets: List<BucketDto>
)

@Serializable
data class BucketDto(
    val bucket: String,
    val category: CategoryDto?,
    val name: String,
    val total: String,
    val share: Double
)

@Serializable
data class MerchantSpendingResponse(
    val period: PeriodDto,
    val currency: String,
    val total: String,
    val merchants: List<MerchantRowDto>
)

@Serializable
data class MerchantRowDto(
    val merchant: MerchantRefDto,
    val total: String,
    val receipts: Int
)

@Serializable
data class MerchantRefDto(
    val id: String,
    val display_name: String
)

@Serializable
data class TrendResponse(
    val period: PeriodDto,
    val currency: String,
    val months: List<MonthTrendDto>
)

@Serializable
data class MonthTrendDto(
    val month: String,
    val total: String,
    val receipts: Int
)

@Serializable
data class TopProductsResponse(
    val period: PeriodDto,
    val currency: String,
    val by: String,
    val products: List<TopProductDto>
)

@Serializable
data class TopProductDto(
    val product: ProductRefDto,
    val receipts: Int,
    val spend: String
)

@Serializable
data class ProductRefDto(
    val id: String,
    val name: String
)
