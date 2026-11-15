"""Reporting periods in the household timezone (requirements §13). Pure Python."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo


@dataclass(frozen=True)
class Period:
    """Calendar days ``first``..``last``, both inclusive."""

    first: date
    last: date

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1

    def previous(self) -> "Period":
        """The period of the same length immediately before."""
        last = self.first - timedelta(days=1)
        return Period(last - timedelta(days=self.days - 1), last)

    def bounds(self, tz: tzinfo) -> tuple[datetime, datetime]:
        """[start, end) as aware datetimes: local midnights, so DST changes are respected."""
        start = datetime.combine(self.first, time.min, tzinfo=tz)
        end = datetime.combine(self.last + timedelta(days=1), time.min, tzinfo=tz)
        return start, end


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(month: date, count: int) -> date:
    """The first day of the month ``count`` months after ``month`` (negative: before)."""
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def month_period(day: date) -> Period:
    first = month_start(day)
    return Period(first, add_months(first, 1) - timedelta(days=1))


def months_ending(day: date, count: int) -> Period:
    """``count`` calendar months, the last one being the month of ``day``."""
    last_month = month_start(day)
    return Period(add_months(last_month, -(count - 1)), month_period(day).last)
