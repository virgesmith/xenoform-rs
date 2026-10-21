from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from xenoform_rs import rust, rust_dependency

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


# pyo3 0.29.3's Zoned -> datetime conversion never sets fold=1: its fold() compares against the offset *after* the
# preceding transition. jiff computes 01:30 GMT correctly, but python reads fold=0 as 01:30 BST, an hour early.
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
