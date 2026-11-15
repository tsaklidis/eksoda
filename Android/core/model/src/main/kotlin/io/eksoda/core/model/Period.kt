package io.eksoda.core.model

import java.time.LocalDate
import java.time.YearMonth

sealed class Period {
    abstract val start: LocalDate
    abstract val end: LocalDate

    data class Month(val yearMonth: YearMonth) : Period() {
        override val start: LocalDate = yearMonth.atDay(1)
        override val end: LocalDate = yearMonth.atEndOfMonth()
    }

    data class Range(override val start: LocalDate, override val end: LocalDate) : Period()

    companion object {
        fun current(): Month = Month(YearMonth.now())
        fun lastMonth(): Month = Month(YearMonth.now().minusMonths(1))
    }
}
