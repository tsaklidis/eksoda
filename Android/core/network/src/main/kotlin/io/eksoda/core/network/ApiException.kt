package io.eksoda.core.network

import io.eksoda.core.network.model.ErrorDetail
import java.io.IOException

class ApiException(
    val code: String,
    override val message: String,
    val details: Map<String, List<String>> = emptyMap(),
    val httpStatus: Int
) : IOException(message) {
    companion object {
        fun fromErrorDetail(detail: ErrorDetail, httpStatus: Int): ApiException {
            return ApiException(
                code = detail.code,
                message = detail.message,
                details = detail.details,
                httpStatus = httpStatus
            )
        }
    }
}
