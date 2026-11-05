from datetime import datetime, time as Time
from types import SimpleNamespace

import pandas as pd
import pytest

from bullet_trade.data import api as data_api
from bullet_trade.data.providers.base import DataProvider
from bullet_trade.core.settings import reset_settings


class FakeProvider(DataProvider):
    name = "fake"

    def __init__(self):
        self.daily_prev = pd.DataFrame(
            {
                "open": [99.5],
                "close": [100.299],
                "high_limit": [110.194],
                "low_limit": [90.158],
                "paused": [0.0],
            },
            index=[pd.Timestamp("2014-12-31 15:00:00")],
        )
        self.daily_today = pd.DataFrame(
            {
                "open": [101.0],
                "close": [101.5],
                "high_limit": [111.65],
                "low_limit": [91.35],
                "paused": [0.0],
            },
            index=[pd.Timestamp("2015-01-05 15:00:00")],
        )
        self.minute_first = pd.DataFrame(
            {
                "open": [101.0],
                "close": [105.0],
                "high_limit": [111.65],
                "low_limit": [91.35],
                "paused": [0.0],
            },
            index=[pd.Timestamp("2015-01-05 09:31:00")],
        )

    def auth(self, *_, **__):
        return None

    def get_price(
        self,
        security,
        start_date=None,
        end_date=None,
        frequency="daily",
        fields=None,
        skip_paused=False,
        fq="pre",
        count=None,
        panel=True,
        fill_paused=True,
        pre_factor_ref_date=None,
        prefer_engine=False,
    ):
        end_dt = pd.to_datetime(end_date) if end_date is not None else None
        if frequency == "minute":
            return self.minute_first.copy()
        if end_dt is not None and isinstance(end_dt, datetime):
            if end_dt.time() < Time(9, 30):
                return self.daily_prev.copy()
            return self.daily_today.copy()
        return self.daily_today.copy()

    def get_trade_days(self, *_, **__):
        return []

    def get_all_securities(self, *_, **__):
        return pd.DataFrame()

    def get_index_stocks(self, *_, **__):
        return []

    def get_split_dividend(self, *_, **__):
        return []


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def fake_provider():
    original_provider = data_api._provider
    original_auth_attempted = data_api._auth_attempted
    original_context = data_api._current_context
    provider = FakeProvider()
    data_api.set_data_provider(provider)
    yield provider
    data_api._provider = original_provider
    data_api._auth_attempted = original_auth_attempted
    data_api.set_current_context(original_context)


def _set_context(dt: datetime):
    context = SimpleNamespace(current_dt=dt)
    data_api.set_current_context(context)
    return data_api.get_current_data()


def test_current_data_uses_previous_close_before_open(fake_provider):
    current_data = _set_context(datetime(2015, 1, 5, 9, 0))
    data = current_data["000001.XSHE"]
    assert data.last_price == pytest.approx(100.299)


def test_current_data_uses_daily_open_at_call_auction(fake_provider):
    current_data = _set_context(datetime(2015, 1, 5, 9, 30))
    data = current_data["000001.XSHE"]
    assert data.last_price == pytest.approx(101.0)


def test_current_data_uses_minute_after_first_bar(fake_provider):
    current_data = _set_context(datetime(2015, 1, 5, 9, 31))
    data = current_data["000001.XSHE"]
    assert data.last_price == pytest.approx(105.0)


def test_limit_fallback_uses_pre_close_instead_of_current_minute_price(monkeypatch):
    monkeypatch.setattr(data_api, "_resolve_limit_ratio", lambda _security: 0.2)
    monkeypatch.setattr(data_api, "_fetch_pre_close", lambda *args, **kwargs: 80.0)

    high_limit, low_limit = data_api._apply_limit_fallback(
        "300394.XSHE",
        datetime(2025, 5, 30, 14, 50),
        81.71,
        0.0,
        0.0,
        False,
        False,
    )

    assert high_limit == pytest.approx(96.0)
    assert low_limit == pytest.approx(64.0)
    assert high_limit != pytest.approx(81.71)
