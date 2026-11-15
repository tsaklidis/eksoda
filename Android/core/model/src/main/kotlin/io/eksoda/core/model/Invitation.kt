package io.eksoda.core.model

import java.time.OffsetDateTime

data class Invitation(
    val id: String,
    val code: String,
    val createdBy: String,
    val createdAt: OffsetDateTime,
    val expiresAt: OffsetDateTime?,
    val usedAt: OffsetDateTime?,
    val usedBy: String?
) {
    val isPending: Boolean get() = usedAt == null && (expiresAt == null || expiresAt.isAfter(OffsetDateTime.now()))
}
