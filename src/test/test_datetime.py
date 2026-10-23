from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from typing import Annotated
from zoneinfo import ZoneInfo

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from xenoform_rs import NUMPY_CRATE, rust, rust_dependency

JIFF = rust_dependency("jiff", version="0.2")


# pandas-stubs type every Timestamp/Timedelta constructor as possibly NaT; narrow so they type-check as datetime/timedelta
def _ts(value: str, tz: str | None = None) -> pd.Timestamp:
    ts = pd.Timestamp(value, tz=tz)
    assert isinstance(ts, pd.Timestamp)
    return ts


def _td(hours: float = 0) -> pd.Timedelta:
    td = pd.Timedelta(hours=hours)
    assert isinstance(td, pd.Timedelta)
    return td


@rust(py=False, dependencies=[JIFF])
def shift(t: datetime, dt: timedelta) -> datetime:  # ty: ignore[empty-body]
    """
    Ok(t.checked_add(dt)?)
    """


# naive datetimes need the civil type override: the default jiff::Zoned requires a tzinfo
@rust(py=False, dependencies=[JIFF])
def shift_naive(
    t: Annotated[datetime, "jiff::civil::DateTime"], dt: timedelta
) -> Annotated[datetime, "jiff::civil::DateTime"]:  # ty: ignore[empty-body]
    """
    Ok(t.checked_add(dt)?)
    """


@rust(py=False, dependencies=[JIFF])
def next_day(d: date) -> date:  # ty: ignore[empty-body]
    """
    Ok(d.tomorrow()?)
    """


@rust(py=False, dependencies=[JIFF])
def add_minutes(t: time, m: int) -> time:  # ty: ignore[empty-body]
    """
    Ok(t.wrapping_add(jiff::SignedDuration::from_mins(m.into())))
    """


@rust(py=False, dependencies=[JIFF])
def in_zone(t: datetime, tz: tzinfo) -> datetime:  # ty: ignore[empty-body]
    """
    Ok(t.with_time_zone(tz))
    """


@rust(py=False, dependencies=[JIFF])
def zone_of(t: datetime) -> tzinfo:  # ty: ignore[empty-body]
    """
    Ok(t.time_zone().clone())
    """


@rust(py=False, dependencies=[JIFF])
def zone_name(t: datetime) -> str | None:
    """
    Ok(t.time_zone().iana_name().map(String::from))
    """


@rust(py=False, dependencies=[JIFF])
def hours_since_start(t: list[datetime]) -> list[float]:  # ty: ignore[empty-body]
    """
    let Some(start) = t.first() else {
        return Ok(Vec::new());
    };
    Ok(t.iter().map(|ti| ti.duration_since(start).as_secs_f64() / 3600.0).collect())
    """


@rust(py=False, dependencies=[JIFF])
def count_missing(t: list[datetime | None]) -> int:  # ty: ignore[empty-body]
    """
    Ok(t.iter().filter(|ti| ti.is_none()).count() as i32)
    """


@rust(
    py=False,
    dependencies=[NUMPY_CRATE],
    imports=["numpy::PyReadonlyArray1", "numpy::datetime::{Datetime, units::Microseconds}"],
)
def count_nat(
    t: Annotated[npt.NDArray[np.datetime64], "PyReadonlyArray1<'py, Datetime<Microseconds>>"],
) -> int:  # ty: ignore[empty-body]
    """
    // numpy stores NaT as i64::MIN
    Ok(t.as_array().iter().filter(|&&ti| i64::from(ti) == i64::MIN).count() as i32)
    """


@rust(py=False, dependencies=[JIFF])
def scale(dt: timedelta, k: int) -> timedelta:  # ty: ignore[empty-body]
    """
    Ok(dt * k)
    """


@pytest.mark.parametrize(
    "tz", [UTC, timezone(timedelta(hours=-5)), timezone(timedelta(hours=5, minutes=30)), ZoneInfo("Europe/London")]
)
def test_any_timezone_round_trips(tz: timezone | ZoneInfo) -> None:
    t = datetime(2026, 7, 1, 12, 34, 56, 789, tzinfo=tz)
    result = shift(t, timedelta(hours=1))
    assert result == t + timedelta(hours=1)
    assert result.utcoffset() == t.utcoffset()
    assert result.tzinfo == tz


def test_named_zone_follows_dst_rules() -> None:
    # UK clocks go back at 02:00 BST on 2026-10-25: three elapsed hours from 00:30 BST is 02:30 GMT
    t = datetime(2026, 10, 25, 0, 30, tzinfo=ZoneInfo("Europe/London"))
    result = shift(t, timedelta(hours=3))
    assert result.tzname() == "GMT"
    assert (result.hour, result.minute) == (2, 30)
    assert result.astimezone(UTC) - t.astimezone(UTC) == timedelta(hours=3)


# pyo3's Zoned -> datetime conversion (still in 0.30) never sets fold=1: its fold() compares against the offset *after*
# the preceding transition. jiff computes 01:30 GMT correctly, but python reads fold=0 as 01:30 BST, an hour early.
# Remove the xfail once pyo3 fixes the fold calculation (strict, so the fix is noticed).
@pytest.mark.xfail(strict=True, reason="pyo3 jiff conversion loses fold in the repeated hour")
def test_repeated_hour_keeps_fold() -> None:
    t = datetime(2026, 10, 25, 0, 30, tzinfo=ZoneInfo("Europe/London"))
    result = shift(t, timedelta(hours=2))
    assert result.fold == 1
    assert result.tzname() == "GMT"
    assert result.astimezone(UTC) - t.astimezone(UTC) == timedelta(hours=2)


def test_zone_name_is_visible_to_rust() -> None:
    assert zone_name(datetime.now(ZoneInfo("Europe/London"))) == "Europe/London"
    assert zone_name(datetime.now(timezone(timedelta(hours=1)))) is None


def test_naive_datetime_rejected() -> None:
    with pytest.raises(TypeError, match="non-None tzinfo"):
        shift(datetime(2026, 1, 1), timedelta(0))


def test_naive_datetime_via_civil_override() -> None:
    t = datetime(2026, 7, 1, 12, 34, 56, 789)
    result = shift_naive(t, timedelta(hours=1))
    assert result == datetime(2026, 7, 1, 13, 34, 56, 789)
    assert result.tzinfo is None
    assert shift_naive(_ts("2026-07-01 12:00"), _td(hours=1)) == datetime(2026, 7, 1, 13)


def test_civil_override_rejects_aware_datetime() -> None:
    with pytest.raises(TypeError, match="without tzinfo"):
        shift_naive(datetime(2026, 1, 1, tzinfo=UTC), timedelta(0))


def test_civil_arithmetic_is_wall_clock() -> None:
    # no zone, so no DST: across the UK clocks going back, 00:30 + 2h is 02:30 (3 real hours in London)
    assert shift_naive(datetime(2026, 10, 25, 0, 30), timedelta(hours=2)) == datetime(2026, 10, 25, 2, 30)


def test_timedelta_round_trips() -> None:
    assert scale(timedelta(days=1, microseconds=1), 3) == timedelta(days=3, microseconds=3)
    assert scale(timedelta(seconds=-1.5), 2) == timedelta(seconds=-3)


@pytest.mark.parametrize("tz", ["UTC", "+05:30", "Europe/London"])
def test_pandas_timestamp_round_trips(tz: str) -> None:
    ts = _ts("2026-07-01 12:34:56.789", tz=tz)
    result = shift(ts, _td(hours=1))
    assert result == ts + _td(hours=1)
    assert result.utcoffset() == ts.utcoffset()


def test_pandas_timestamp_zone_name() -> None:
    assert zone_name(pd.Timestamp.now(tz="Europe/London")) == "Europe/London"


def test_pandas_timestamp_nanoseconds_truncated() -> None:
    # jiff::Zoned has nanosecond precision but pyo3 converts via the datetime fields, which stop at microseconds
    ts = _ts("2026-07-01 12:00:00.000001999", tz="UTC")
    result = shift(ts, _td())
    assert pd.Timestamp(result) == ts.floor("us")


def test_naive_pandas_timestamp_rejected() -> None:
    with pytest.raises(TypeError, match="non-None tzinfo"):
        shift(_ts("2026-01-01"), _td())


def test_pandas_index_as_list() -> None:
    # 2026-10-25 has 25 hours in London: an hourly local index is still one elapsed hour apart throughout
    day = pd.Timestamp("2026-10-25", tz="Europe/London")
    idx = pd.date_range(day, day + pd.DateOffset(days=1), freq="h", inclusive="left")
    assert len(idx) == 25
    assert hours_since_start(list(idx)) == [float(h) for h in range(25)]
    assert hours_since_start([]) == []


def test_date_round_trips() -> None:
    assert next_day(date(2026, 10, 21)) == date(2026, 10, 22)
    assert next_day(date(2028, 2, 28)) == date(2028, 2, 29)
    assert next_day(date(2026, 12, 31)) == date(2027, 1, 1)


def test_datetime_passed_as_date_loses_time() -> None:
    # datetime subclasses date, so pyo3 accepts it and reads only the date fields
    result = next_day(datetime(2026, 10, 21, 18, 30, tzinfo=UTC))
    assert type(result) is date
    assert result == date(2026, 10, 22)


def test_time_round_trips() -> None:
    assert add_minutes(time(12, 0, 0, 123456), 0) == time(12, 0, 0, 123456)
    assert add_minutes(time(23, 30), 45) == time(0, 15)


def test_time_drops_tzinfo() -> None:
    # a time-of-day offset can't account for DST, and pyo3 reads only the clock fields
    result = add_minutes(time(12, tzinfo=UTC), 0)
    assert result == time(12)
    assert result.tzinfo is None


@pytest.mark.parametrize("tz", [UTC, timezone(timedelta(hours=5, minutes=30)), ZoneInfo("Europe/London")])
def test_tzinfo_round_trips(tz: timezone | ZoneInfo) -> None:
    assert zone_of(datetime(2026, 7, 1, tzinfo=tz)) == tz


def test_tzinfo_argument() -> None:
    t = datetime(2026, 7, 1, 12, tzinfo=UTC)
    result = in_zone(t, ZoneInfo("Europe/London"))
    assert result == t
    assert result.tzinfo == ZoneInfo("Europe/London")
    assert (result.hour, result.tzname()) == (13, "BST")


# pd.NaT is a datetime subclass with no data, and isn't None, so `datetime | None` doesn't help: replace NaT with None
# first, or pass a datetime64 array. Zoned always rejects it: its tzinfo is None
def test_nat_rejected_as_zoned() -> None:
    with pytest.raises(TypeError, match="non-None tzinfo"):
        shift(pd.NaT, _td())  # ty: ignore[invalid-argument-type]


# date and civil types read NaT's date fields, which hold 0001-01-01, so NaT is silently read as that date. Under pyo3
# 0.29 this happened only on free-threaded builds, and the stable ABI build raised TypeError. Since 0.30 every build does it
def test_nat_silently_read_as_date() -> None:
    assert next_day(pd.NaT) == date(1, 1, 2)  # ty: ignore[invalid-argument-type]


def test_nat_in_list_rejected_until_replaced_with_none() -> None:
    idx = pd.DatetimeIndex([_ts("2026-01-01", tz="UTC"), pd.NaT, _ts("2026-01-02", tz="UTC")])
    with pytest.raises(TypeError, match="non-None tzinfo"):
        count_missing(list(idx))
    assert count_missing(list(idx.astype(object).where(idx.notna(), None))) == 1


def test_nat_in_datetime64_array_is_i64_min() -> None:
    idx = pd.DatetimeIndex([_ts("2026-01-01", tz="UTC"), pd.NaT, pd.NaT])
    assert count_nat(idx.tz_convert(None).as_unit("us").to_numpy()) == 2
