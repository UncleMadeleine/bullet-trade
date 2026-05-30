import pytest
from unittest import mock
from datetime import datetime, date as Date

import pandas as pd

from bullet_trade.data.providers.mysquant import MysQuantProvider


class TestMysQuantProviderCodeConversion:
    """Test code format conversion utilities."""

    def test_to_mysquant_code(self):
        assert MysQuantProvider._to_mysquant_code("600000.XSHG") == "SHSE.600000"
        assert MysQuantProvider._to_mysquant_code("000001.XSHE") == "SZSE.000001"
        assert MysQuantProvider._to_mysquant_code("600000") == "600000"
        assert MysQuantProvider._to_mysquant_code("SHSE.600000") == "SHSE.600000"

    def test_to_jq_code(self):
        assert MysQuantProvider._to_jq_code("SHSE.600000") == "600000.XSHG"
        assert MysQuantProvider._to_jq_code("SZSE.000001") == "000001.XSHE"
        assert MysQuantProvider._to_jq_code("600000") == "600000"
        assert MysQuantProvider._to_jq_code("600000.XSHG") == "600000.XSHG"


class TestMysQuantProviderFrequency:
    """Test frequency normalization."""

    def test_normalize_frequency_daily(self):
        assert MysQuantProvider()._normalize_frequency("daily") == "1d"
        assert MysQuantProvider()._normalize_frequency("1d") == "1d"
        assert MysQuantProvider()._normalize_frequency("d") == "1d"

    def test_normalize_frequency_minute(self):
        assert MysQuantProvider()._normalize_frequency("minute") == "60s"
        assert MysQuantProvider()._normalize_frequency("1m") == "60s"
        assert MysQuantProvider()._normalize_frequency("m1") == "60s"

    def test_normalize_frequency_minutes_mapping(self):
        assert MysQuantProvider()._normalize_frequency("5m") == "300s"
        assert MysQuantProvider()._normalize_frequency("15m") == "900s"
        assert MysQuantProvider()._normalize_frequency("30m") == "1800s"
        assert MysQuantProvider()._normalize_frequency("60m") == "3600s"

    def test_normalize_frequency_seconds(self):
        assert MysQuantProvider()._normalize_frequency("60s") == "60s"
        assert MysQuantProvider()._normalize_frequency("300s") == "300s"


class TestMysQuantProviderDateFormatter:
    """Test date formatting utilities."""

    def test_to_date_str(self):
        assert MysQuantProvider._to_date_str(None) is None
        assert MysQuantProvider._to_date_str("2024-01-01") == "2024-01-01"
        assert MysQuantProvider._to_date_str(Date(2024, 1, 1)) == "2024-01-01"
        assert MysQuantProvider._to_date_str(datetime(2024, 1, 1, 10, 0)) == "2024-01-01"

    def test_to_datetime_str(self):
        assert MysQuantProvider._to_datetime_str(None) is None
        assert MysQuantProvider._to_datetime_str("2024-01-01 10:00:00") == "2024-01-01 10:00:00"
        assert MysQuantProvider._to_datetime_str(datetime(2024, 1, 1, 10, 0)) == "2024-01-01 10:00:00"


class TestMysQuantProviderInitialization:
    """Test provider initialization and authentication."""

    def test_init_without_token_does_not_raise(self):
        # Should not raise until auth() is called
        provider = MysQuantProvider()
        assert provider.name == "mysquant"
        assert provider.requires_live_data is True

    def test_auth_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("MYSQUANT_TOKEN", raising=False)
        monkeypatch.delenv("MYQUANT_TOKEN", raising=False)
        provider = MysQuantProvider()
        with pytest.raises(RuntimeError, match="MYSQUANT_TOKEN"):
            provider.auth()

    def test_auth_with_token(self, monkeypatch):
        mock_set_token = mock.MagicMock()
        monkeypatch.setattr("gm.api.set_token", mock_set_token)
        provider = MysQuantProvider(config={"token": "test_token"})
        provider.auth()
        mock_set_token.assert_called_once_with("test_token")


class TestMysQuantProviderGetPrice:
    """Test get_price method."""

    def test_get_price_requires_auth(self, monkeypatch):
        monkeypatch.delenv("MYSQUANT_TOKEN", raising=False)
        monkeypatch.delenv("MYQUANT_TOKEN", raising=False)
        provider = MysQuantProvider()
        with pytest.raises(RuntimeError):
            provider.get_price("SHSE.600000")

    def test_get_price_converts_code(self, monkeypatch):
        mock_history = mock.MagicMock(return_value=pd.DataFrame({
            "eob": ["2024-01-01 09:30:00"],
            "open": [100.0],
            "close": [101.0],
            "high": [102.0],
            "low": [99.0],
            "volume": [1000],
            "amount": [101000.0],
        }))
        monkeypatch.setattr("gm.api.history", mock_history)
        monkeypatch.setattr("gm.api.set_token", mock.MagicMock())

        provider = MysQuantProvider(config={"token": "test"})
        provider.auth()
        provider.get_price("600000.XSHG", start_date="2024-01-01", end_date="2024-01-01")
        # Verify history called with mysquant code
        call_args = mock_history.call_args
        assert call_args[1]["symbol"] == "SHSE.600000"

    def test_get_price_panel_format(self, monkeypatch):
        mock_history = mock.MagicMock(return_value=pd.DataFrame({
            "eob": ["2024-01-01 09:30:00"],
            "open": [100.0],
            "close": [101.0],
        }))
        monkeypatch.setattr("gm.api.history", mock_history)
        monkeypatch.setattr("gm.api.set_token", mock.MagicMock())

        provider = MysQuantProvider(config={"token": "test"})
        provider.auth()
        result = provider.get_price(["SHSE.600000", "SZSE.000001"], start_date="2024-01-01", end_date="2024-01-01", panel=True)
        assert isinstance(result, pd.DataFrame)
        # MultiIndex columns: first level codes, second level fields
        assert isinstance(result.columns, pd.MultiIndex)
        # Both codes should appear in the first level
        codes = result.columns.get_level_values(0).unique().tolist()
        assert "SHSE.600000" in codes or "600000.XSHG" in codes  # depends on conversion

    def test_get_price_long_format(self, monkeypatch):
        mock_history = mock.MagicMock(return_value=pd.DataFrame({
            "eob": ["2024-01-01 09:30:00"],
            "open": [100.0],
            "close": [101.0],
        }))
        monkeypatch.setattr("gm.api.history", mock_history)
        monkeypatch.setattr("gm.api.set_token", mock.MagicMock())

        provider = MysQuantProvider(config={"token": "test"})
        provider.auth()
        # 多标的 + panel=False 才会产出 long 格式（含 code 列）
        result = provider.get_price(["SHSE.600000", "SZSE.000001"], start_date="2024-01-01", end_date="2024-01-01", panel=False)
        assert isinstance(result, pd.DataFrame)
        assert "code" in result.columns
        assert "close" in result.columns or ("close",) in result.columns  # depends on conversion


class TestMysQuantProviderTradeDays:
    """Test get_trade_days."""

    def test_get_trade_days_requires_auth(self, monkeypatch):
        monkeypatch.delenv("MYSQUANT_TOKEN", raising=False)
        monkeypatch.delenv("MYQUANT_TOKEN", raising=False)
        provider = MysQuantProvider()
        with pytest.raises(RuntimeError):
            provider.get_trade_days()

    def test_get_trade_days_calls_calendar(self, monkeypatch):
        mock_calendar = mock.MagicMock(return_value=["2024-01-01", "2024-01-02"])
        monkeypatch.setattr("gm.api.get_trading_calendar", mock_calendar)
        monkeypatch.setattr("gm.api.set_token", mock.MagicMock())

        provider = MysQuantProvider(config={"token": "test"})
        provider.auth()
        days = provider.get_trade_days(start_date="2024-01-01", end_date="2024-01-02")
        assert len(days) == 2
        mock_calendar.assert_called_once()


class TestMysQuantProviderAllSecurities:
    """Test get_all_securities."""

    def test_get_all_securities_requires_auth(self, monkeypatch):
        monkeypatch.delenv("MYSQUANT_TOKEN", raising=False)
        monkeypatch.delenv("MYQUANT_TOKEN", raising=False)
        provider = MysQuantProvider()
        with pytest.raises(RuntimeError):
            provider.get_all_securities()

    def test_get_all_securities_filters_by_date(self, monkeypatch):
        # Mock get_symbol_infos to return a security with listed_delisted dates
        mock_infos = [
            {"symbol": "SHSE.600000", "name": "Test Bank", "listed_date": "2020-01-01", "delisted_date": None},
        ]
        monkeypatch.setattr("gm.api.get_symbol_infos", lambda **kwargs: mock_infos)
        monkeypatch.setattr("gm.api.set_token", mock.MagicMock())

        provider = MysQuantProvider(config={"token": "test"})
        provider.auth()
        # Query a date after listed
        df = provider.get_all_securities(types="stock", date="2021-06-01")
        assert not df.empty
        assert "600000.XSHG" in df.index
        # Query a date before listed
        df2 = provider.get_all_securities(types="stock", date="2019-06-01")
        assert df2.empty


# Additional tests could cover:
# - get_index_stocks
# - get_security_info
# - get_split_dividend
# - get_current_tick
# - get_live_current
# - error handling and fallbacks
