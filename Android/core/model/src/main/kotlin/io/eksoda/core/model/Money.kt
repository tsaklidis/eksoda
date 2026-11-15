package io.eksoda.core.model

import java.math.BigDecimal
import java.math.RoundingMode

data class Money(
    val amount: BigDecimal,
    val currency: String
) {
    companion object {
        val ZERO = Money(BigDecimal.ZERO, "")
        
        fun fromString(amount: String, currency: String): Money {
            return Money(BigDecimal(amount), currency)
        }
    }

    operator fun plus(other: Money): Money {
        require(currency == other.currency || currency.isEmpty() || other.currency.isEmpty()) {
            "Cannot add different currencies: $currency and ${other.currency}"
        }
        val targetCurrency = if (currency.isNotEmpty()) currency else other.currency
        return Money(amount.add(other.amount), targetCurrency)
    }

    fun format(decimals: Int = 2): String {
        return amount.setScale(decimals, RoundingMode.HALF_UP).toPlainString()
    }
}
