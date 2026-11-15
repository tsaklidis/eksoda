package io.eksoda.core.model

import java.time.OffsetDateTime

data class ImportJob(
    val id: String,
    val status: ImportStatus,
    val outcome: ImportOutcome?,
    val providerCode: String,
    val submittedUrl: String,
    val createdAt: OffsetDateTime,
    val finishedAt: OffsetDateTime?,
    val receiptId: String?,
    val error: ImportError?
)

enum class ImportStatus {
    PENDING, COMPLETED, FAILED
}

enum class ImportOutcome {
    CREATED, DUPLICATE, RECEIPT_DELETED
}

data class ImportError(
    val code: String,
    val message: String
)
