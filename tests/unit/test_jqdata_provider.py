import datetime as dt
import logging

import pandas as pd
import pytest

import bullet_trade.data.providers.jqdata as jqdata
from bullet_trade.data.providers.jqdata import JQDataProvider


@pytest.mark.unit
class TestJQDataProviderAuth:
    def test_auth_prefers_new_env_names(self, monkeypatch):
        provider = JQDataProvider()
        recorded = {}

        def fake_auth(user, pwd, host=None, port=None):
            payload = {"user": user, "pwd": pwd}
            if host is not None:
                payload["host"] = host
            if port is not None:
                payload["port"] = port
            recorded.update(payload)

        monkeypatch.setattr(jqdata.jq, "auth", fake_auth)

        for legacy_key in ("JQDATA_USER", "JQDATA_PWD"):
            monkeypatch.delenv(legacy_key, raising=False)

        monkeypatch.setenv("JQDATA_USERNAME", "new_user")
        monkeypatch.setenv("JQDATA_PASSWORD", "new_pwd")
        monkeypatch.setenv("JQDATA_SERVER", "srv.test")
        monkeypatch.setenv("JQDATA_PORT", "1234")

        provider.auth()

        assert recorded == {
            "user": "new_user",
            "pwd": "new_pwd",
            "host": "srv.test",
            "port": 1234,
        }

    def test_auth_falls_back_to_legacy_env_names(self, monkeypatch):
        provider = JQDataProvider()
        recorded = {}

        def fake_auth(user, pwd, host=None, port=None):
            payload = {"user": user, "pwd": pwd}
            if host is not None:
                payload["host"] = host
            if port is not None:
                payload["port"] = port
            recorded.update(payload)

        monkeypatch.setattr(jqdata.jq, "auth", fake_auth)

        for new_key in ("JQDATA_USERNAME", "JQDATA_PASSWORD"):
            monkeypatch.delenv(new_key, raising=False)

        monkeypatch.setenv("JQDATA_USER", "legacy_user")
        monkeypatch.setenv("JQDATA_PWD", "legacy_pwd")
        monkeypatch.setenv("JQDATA_SERVER", "")
        monkeypatch.setenv("JQDATA_PORT", "")

        provider.auth()

        assert recorded == {
            "user": "legacy_user",
            "pwd": "legacy_pwd",
        }

    def test_auth_strips_inline_comments_from_port(self, monkeypatch):
        provider = JQDataProvider()
        recorded = {}

        def fake_auth(user, pwd, host=None, port=None):
            payload = {"user": user, "pwd": pwd}
            if host is not None:
                payload["host"] = host
            if port is not None:
                payload["port"] = port
            recorded.update(payload)

        monkeypatch.setattr(jqdata.jq, "auth", fake_auth)

        monkeypatch.setenv("JQDATA_USERNAME", "comment_user")
        monkeypatch.setenv("JQDATA_PASSWORD", "comment_pwd")
        monkeypatch.setenv("JQDATA_SERVER", "srv.test")
        monkeypatch.setenv("JQDATA_PORT", "8087                   # 可选：端口")

        provider.auth()

        assert recorded == {
            "user": "comment_user",
            "pwd": "comment_pwd",
            "host": "srv.test",
            "port": 8087,
        }

    def test_auth_strips_inline_comments_from_host(self, monkeypatch):
        provider = JQDataProvider()
        recorded = {}

        def fake_auth(user, pwd, host=None, port=None):
            payload = {"user": user, "pwd": pwd}
            if host is not None:
                payload["host"] = host
            if port is not None:
                payload["port"] = port
            recorded.update(payload)

        monkeypatch.setattr(jqdata.jq, "auth", fake_auth)

        monkeypatch.setenv("JQDATA_USERNAME", "host_user")
        monkeypatch.setenv("JQDATA_PASSWORD", "host_pwd")
        monkeypatch.setenv("JQDATA_SERVER", "")  # 清空，或设置带注释的测试值
        monkeypatch.setenv("JQDATA_PORT", "")  # 清空

        provider.auth()

        assert recorded == {
            "user": "host_user",
            "pwd": "host_pwd",
        }


class _DummyQuery:
    def filter(self, *args, **kwargs):
        return self


class _DummyFinance:
    """JQData 分红单测专用 finance 假对象，避免访问真实 jqdatasdk finance 模块。"""

    STK_XR_XD = jqdata._FINANCE_TABLE_STUB
    FUND_DIVIDEND = jqdata._FINANCE_TABLE_STUB
    FUND_MF_DAILY_PROFIT = jqdata._FINANCE_TABLE_STUB

    def __init__(self, df):
        """
        初始化假 finance 对象。

        Args:
            df: run_query 需要返回的 DataFrame。

        Returns:
            None。仅保存内存 DataFrame。
        """
        self._df = df

    def run_query(self, q):
        """
        返回预置查询结果。

        Args:
            q: 兼容 finance.run_query 的查询对象，测试中不使用。

        Returns:
            pd.DataFrame: 初始化时传入的分红测试数据。
        """
        _ = q
        return self._df


class _RecordingQuery:
    def __init__(self, *columns):
        self.columns = columns
        self.filters = []
        self.order_field = None
        self.limit_value = None

    def filter(self, *args, **kwargs):
        self.filters.extend(args)
        return self

    def order_by(self, field):
        self.order_field = field
        return self

    def limit(self, value):
        self.limit_value = value
        return self


class _RecordingFinance:
    STK_AH_PRICE_COMP = jqdata._FINANCE_TABLE_STUB

    def __init__(self):
        self.queries = []

    def run_query(self, statement):
        self.queries.append(statement)
        return pd.DataFrame(
            [{"day": dt.date(2024, 1, 1), "h_a_comp": 1.0 + len(self.queries)}]
        )


class _RangeColumn:
    """记录比较条件，便于假 finance 按日期区间返回不同行数。"""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ge__(self, other):
        return ("ge", self.name, other)

    def __le__(self, other):
        return ("le", self.name, other)


class _RangeTable:
    def __getattr__(self, name):
        return _RangeColumn(name)


class _RangeFinance:
    STK_AH_PRICE_COMP = _RangeTable()

    def __init__(self, rows_per_day):
        self.rows_per_day = rows_per_day
        self.queries = []

    def run_query(self, statement):
        self.queries.append(statement)
        bounds = {item[0]: item[2] for item in statement.filters}
        start = bounds["ge"]
        end = bounds["le"]
        days = (end - start).days + 1
        rows = min(days * self.rows_per_day, statement.limit_value)
        return pd.DataFrame({"day": [start] * rows})


@pytest.mark.unit
def test_get_finance_table_chunks_by_date(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    fake_finance = _RecordingFinance()
    monkeypatch.setattr(jqdata, "finance", fake_finance)
    monkeypatch.setattr(jqdata, "query", lambda *columns, **kwargs: _RecordingQuery(*columns))

    result = provider.get_finance_table(
        "STK_AH_PRICE_COMP",
        "2024-01-01",
        "2024-01-25",
        fields=["day", "a_code", "h_a_comp"],
        chunk_days=10,
    )

    # 1/1-1/10, 1/11-1/20, 1/21-1/25 三段
    assert len(result) == 3
    assert len(fake_finance.queries) == 3
    assert all(q.limit_value == 3000 for q in fake_finance.queries)
    assert all(q.order_field is not None for q in fake_finance.queries)


@pytest.mark.unit
def test_get_finance_table_subdivides_when_hitting_limit(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    fake_finance = _RangeFinance(rows_per_day=400)
    monkeypatch.setattr(jqdata, "finance", fake_finance)
    monkeypatch.setattr(jqdata, "query", lambda *columns, **kwargs: _RecordingQuery(*columns))

    result = provider.get_finance_table(
        "STK_AH_PRICE_COMP",
        "2024-01-01",
        "2024-01-25",
        chunk_days=10,
    )

    # 10 天分段各 4000 行会触达 3000 上限，二分后 5 天分段不再截断
    assert len(result) == 25 * 400
    # 两个 10 天分段各 3 次查询（父段 + 两个子段），最后 5 天分段 1 次
    assert len(fake_finance.queries) == 7


@pytest.mark.unit
def test_get_finance_table_warns_when_single_day_truncated(monkeypatch, caplog):
    provider = JQDataProvider({"cache_dir": None})
    fake_finance = _RangeFinance(rows_per_day=3000)
    monkeypatch.setattr(jqdata, "finance", fake_finance)
    monkeypatch.setattr(jqdata, "query", lambda *columns, **kwargs: _RecordingQuery(*columns))

    with caplog.at_level(logging.WARNING):
        result = provider.get_finance_table(
            "STK_AH_PRICE_COMP",
            "2024-01-01",
            "2024-01-02",
        )

    assert len(result) == 2 * 3000
    assert any("单日返回达到" in rec.getMessage() for rec in caplog.records)


@pytest.mark.unit
def test_get_finance_table_rejects_unknown_table(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    monkeypatch.setattr(jqdata, "finance", object())
    with pytest.raises(ValueError, match="没有表"):
        provider.get_finance_table("NOT_A_REAL_TABLE", "2024-01-01", "2024-01-02")


@pytest.mark.unit
def test_get_ah_premium_uses_official_fields(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    recorded = {}

    def fake_get_finance_table(table_name, start_date=None, end_date=None, **kwargs):
        recorded.update(
            {
                "table_name": table_name,
                "start_date": start_date,
                "end_date": end_date,
                **kwargs,
            }
        )
        return pd.DataFrame()

    monkeypatch.setattr(provider, "get_finance_table", fake_get_finance_table)
    provider.get_ah_premium("2024-01-01", "2024-01-31")

    assert recorded["table_name"] == "STK_AH_PRICE_COMP"
    assert recorded["start_date"] == "2024-01-01"
    assert recorded["end_date"] == "2024-01-31"
    assert recorded["fields"] == [
        "day",
        "a_code",
        "h_code",
        "a_price",
        "h_price",
        "h_a_comp",
    ]


@pytest.mark.unit
def test_get_split_dividend_prefers_ratio_fields(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    monkeypatch.setattr(
        JQDataProvider,
        "_resolve_security_identity",
        lambda self, security, ref_date: (security, "stock"),
    )
    monkeypatch.setattr(jqdata, "query", lambda *args, **kwargs: _DummyQuery())

    df = pd.DataFrame(
        [
            {
                "a_xr_date": dt.date(2015, 7, 27),
                "bonus_ratio_rmb": 5.0,
                "dividend_ratio": 2.0,
                "transfer_ratio": 1.0,
            }
        ]
    )
    monkeypatch.setattr(jqdata, "finance", _DummyFinance(df))

    events = provider.get_split_dividend(
        "601318.XSHG", start_date="2015-07-27", end_date="2015-07-27"
    )

    assert len(events) == 1
    event = events[0]
    assert event["bonus_pre_tax"] == pytest.approx(5.0)
    assert event["scale_factor"] == pytest.approx(1.3)
    assert event["per_base"] == 10


@pytest.mark.unit
def test_get_split_dividend_falls_back_to_share_base(monkeypatch):
    provider = JQDataProvider({"cache_dir": None})
    monkeypatch.setattr(
        JQDataProvider,
        "_resolve_security_identity",
        lambda self, security, ref_date: (security, "stock"),
    )
    monkeypatch.setattr(jqdata, "query", lambda *args, **kwargs: _DummyQuery())

    df = pd.DataFrame(
        [
            {
                "a_xr_date": dt.date(2015, 7, 27),
                "bonus_ratio_rmb": 4.0,
                "dividend_number": 30000.0,
                "transfer_number": 10000.0,
                "distributed_share_base_implement": 100000.0,
            }
        ]
    )
    monkeypatch.setattr(jqdata, "finance", _DummyFinance(df))

    events = provider.get_split_dividend(
        "601318.XSHG", start_date="2015-07-27", end_date="2015-07-27"
    )

    assert len(events) == 1
    event = events[0]
    assert event["bonus_pre_tax"] == pytest.approx(4.0)
    assert event["scale_factor"] == pytest.approx(1.4)


@pytest.mark.unit
def test_get_split_dividend_resolves_sz_etf_suffix(monkeypatch):
    """验证 JQData provider 用 .SZ 查询 ETF 时仍能读取基金拆分事件。"""
    provider = JQDataProvider({"cache_dir": None})

    def fake_get_all_securities(types="stock", date=None):
        """
        返回测试用证券清单，只在 etf 类型下暴露聚宽后缀代码。

        Args:
            types: 查询的证券类型。
            date: 查询参考日期，测试中不使用。

        Returns:
            pd.DataFrame: 指定类型的证券索引。
        """
        _ = date
        if types == "etf":
            return pd.DataFrame(index=["159967.XSHE"])
        return pd.DataFrame()

    monkeypatch.setattr(provider, "get_all_securities", fake_get_all_securities)
    monkeypatch.setattr(jqdata, "query", lambda *args, **kwargs: _DummyQuery())

    df = pd.DataFrame(
        [
            {
                "ex_date": dt.date(2020, 11, 6),
                "record_date": dt.date(2020, 11, 5),
                "proportion": 0.0,
                "split_ratio": 3.63839094,
            }
        ]
    )
    monkeypatch.setattr(jqdata, "finance", _DummyFinance(df))

    events = provider.get_split_dividend(
        "159967.SZ",
        start_date="2020-11-06",
        end_date="2020-11-06",
    )

    assert len(events) == 1
    event = events[0]
    assert event["security"] == "159967.SZ"
    assert event["security_type"] == "etf"
    assert event["scale_factor"] == pytest.approx(3.63839094)
    assert event["per_base"] == 1
