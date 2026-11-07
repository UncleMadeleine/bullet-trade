"""AkshareProvider 离线单元测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from bullet_trade.data.providers.akshare import AkshareProvider


class FakeAk:
    """模拟 akshare 模块，覆盖 provider 使用的公开接口。"""

    def __init__(self) -> None:
        self.calls = []
        self.empty_periods: set = set()
        self.pb_quantile_nan = False
        self.blank_industry = False

    def stock_zh_a_hist(self, **kwargs) -> pd.DataFrame:
        """返回两行日线数据。"""
        self.calls.append(("stock_zh_a_hist", kwargs))
        return pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 10.0,
                    "收盘": 10.2,
                    "最高": 10.3,
                    "最低": 9.9,
                    "成交量": 12,
                    "成交额": 12240.0,
                },
                {
                    "日期": "2024-01-03",
                    "开盘": 10.2,
                    "收盘": 10.4,
                    "最高": 10.5,
                    "最低": 10.1,
                    "成交量": 13,
                    "成交额": 13520.0,
                },
            ]
        )

    def stock_zh_a_hist_min_em(self, **kwargs) -> pd.DataFrame:
        """返回两行分钟数据。"""
        self.calls.append(("stock_zh_a_hist_min_em", kwargs))
        return pd.DataFrame(
            [
                {
                    "时间": "2024-01-02 09:31:00",
                    "开盘": 10.0,
                    "收盘": 10.1,
                    "最高": 10.2,
                    "最低": 9.9,
                    "成交量": 1,
                    "成交额": 1010.0,
                },
                {
                    "时间": "2024-01-02 09:32:00",
                    "开盘": 10.1,
                    "收盘": 10.2,
                    "最高": 10.3,
                    "最低": 10.0,
                    "成交量": 2,
                    "成交额": 2040.0,
                },
            ]
        )

    def index_zh_a_hist(self, **kwargs) -> pd.DataFrame:
        """返回指数日线。"""
        self.calls.append(("index_zh_a_hist", kwargs))
        return pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 3000.0,
                    "收盘": 3010.0,
                    "最高": 3020.0,
                    "最低": 2990.0,
                    "成交量": 100,
                    "成交额": 10000.0,
                }
            ]
        )

    def tool_trade_date_hist_sina(self) -> pd.DataFrame:
        """返回三个交易日。"""
        return pd.DataFrame(
            {
                "trade_date": [
                    date(2023, 12, 29),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ]
            }
        )

    def stock_info_a_code_name(self) -> pd.DataFrame:
        """返回股票代码列表。"""
        return pd.DataFrame(
            {
                "code": ["000001", "600000"],
                "name": ["平安银行", "浦发银行"],
            }
        )

    def fund_etf_spot_em(self) -> pd.DataFrame:
        """返回 ETF 列表。"""
        return pd.DataFrame(
            {
                "代码": ["510300", "159915"],
                "名称": ["沪深300ETF", "创业板ETF"],
            }
        )

    def fund_lof_spot_em(self) -> pd.DataFrame:
        """返回 LOF 列表。"""
        return pd.DataFrame(
            {
                "代码": ["161725"],
                "名称": ["白酒LOF"],
            }
        )

    def index_stock_info(self) -> pd.DataFrame:
        """返回指数列表。"""
        return pd.DataFrame(
            {
                "index_code": ["000300"],
                "display_name": ["沪深300"],
                "publish_date": [date(2005, 4, 8)],
            }
        )

    def index_stock_cons_csindex(self, symbol: str) -> pd.DataFrame:
        """返回中证指数成分表。"""
        _ = symbol
        return pd.DataFrame(
            {
                "成分券代码": ["600000", "000001"],
                "交易所": ["上海证券交易所", "深圳证券交易所"],
            }
        )

    def index_stock_cons(self, symbol: str) -> pd.DataFrame:
        """返回新浪指数成分表。"""
        _ = symbol
        return pd.DataFrame(
            {
                "品种代码": ["600000"],
            }
        )

    def stock_history_dividend_detail(self, symbol: str, indicator: str) -> pd.DataFrame:
        """返回个股分红详情。"""
        _ = symbol, indicator
        return pd.DataFrame(
            [
                {
                    "除权除息日": date(2024, 6, 20),
                    "送股": 1.0,
                    "转增": 2.0,
                    "派息": 2.5,
                },
                {
                    "除权除息日": date(2023, 6, 20),
                    "送股": 0.0,
                    "转增": 0.0,
                    "派息": 1.5,
                },
            ]
        )

    def stock_individual_info_em(self, symbol: str) -> pd.DataFrame:
        """返回个股基础信息。"""
        _ = symbol
        return pd.DataFrame(
            {
                "item": ["股票简称", "行业", "上市时间"],
                "value": ["平安银行", "银行", 19910403],
            }
        )

    def stock_zh_a_spot_em(self) -> pd.DataFrame:
        """返回实时股票快照; 含市净率/市盈率-动态估值字段。"""
        return pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "最新价": 10.5,
                    "今开": 10.2,
                    "最高": 10.6,
                    "最低": 10.1,
                    "昨收": 10.0,
                    "成交量": 12345,
                    "成交额": 129622500.0,
                    "市净率": 1.2,
                    "市盈率-动态": 8.5,
                },
                {
                    "代码": "600000",
                    "名称": "浦发银行",
                    "最新价": 8.0,
                    "今开": 8.1,
                    "最高": 8.2,
                    "最低": 7.9,
                    "昨收": 8.0,
                    "成交量": 1000,
                    "成交额": 8000000.0,
                    "市净率": 0.9,
                    "市盈率-动态": 5.4,
                },
                {
                    "代码": "300750",
                    "名称": "宁德时代",
                    "最新价": 180.0,
                    "今开": 178.0,
                    "最高": 182.0,
                    "最低": 176.0,
                    "昨收": 179.0,
                    "成交量": 50000,
                    "成交额": 9000000000.0,
                    "市净率": 3.5,
                    "市盈率-动态": 20.1,
                },
            ]
        )


    def stock_a_all_pb(self, **kwargs) -> pd.DataFrame:
        """返回全A中位数PB历史序列; pb_quantile_nan 为真时分位列留空。"""
        self.calls.append(("stock_a_all_pb", kwargs))
        quantile = [None, None, None] if self.pb_quantile_nan else [None, None, 0.425]
        return pd.DataFrame(
            {
                "date": ["2024-01-31", "2024-02-29", "2024-03-31"],
                "middlePB": [2.10, 2.30, 2.20],
                "equalWeightAveragePB": [2.60, 2.70, 2.80],
                "close": [3000.0, 3100.0, 3200.0],
                "quantileInAllHistoryMiddlePB": quantile,
            }
        )

    def stock_yjbb_em(self, **kwargs) -> pd.DataFrame:
        """返回业绩报表; date 命中 empty_periods 时返回空表。"""
        self.calls.append(("stock_yjbb_em", kwargs))
        if kwargs.get("date") in self.empty_periods:
            return pd.DataFrame()
        industry = None if self.blank_industry else "银行Ⅱ"
        return pd.DataFrame(
            [
                {
                    "股票代码": "000001",
                    "股票简称": "平安银行",
                    "净资产收益率": 8.07,
                    "营业总收入-同比增长": 2.42,
                    "每股收益": 0.5,
                    "每股净资产": 10.0,
                    "所处行业": industry,
                },
                {
                    "股票代码": "600000",
                    "股票简称": "浦发银行",
                    "净资产收益率": 5.2,
                    "营业总收入-同比增长": 4.42,
                    "每股收益": 0.3,
                    "每股净资产": 12.0,
                    "所处行业": industry,
                },
            ]
        )


def _provider() -> AkshareProvider:
    """创建注入 fake akshare 的 provider。"""
    return AkshareProvider({"akshare": FakeAk(), "cache_dir": None})


@pytest.mark.unit
def test_akshare_daily_price_normalizes_columns_and_volume() -> None:
    """日线应转换为聚宽列名，并把成交量从手换算为股。"""
    provider = _provider()

    df = provider.get_price(
        "000001.XSHE",
        start_date="2024-01-01",
        end_date="2024-01-31",
        frequency="daily",
        fields=["open", "close", "volume", "money", "paused"],
        fq="pre",
    )

    assert list(df.columns) == ["open", "close", "volume", "money", "paused"]
    assert df.index[0] == pd.Timestamp("2024-01-02")
    assert df.iloc[0]["volume"] == 1200.0
    assert bool(df.iloc[0]["paused"]) is False
    ak = provider._ensure_akshare()
    assert ak.calls[0][0] == "stock_zh_a_hist"
    assert ak.calls[0][1]["adjust"] == "qfq"


@pytest.mark.unit
def test_akshare_minute_price_uses_minute_endpoint() -> None:
    """分钟频率应调用分钟接口并保持时间索引。"""
    provider = _provider()

    df = provider.get_price(
        "000001.XSHE",
        start_date="2024-01-02 09:30:00",
        end_date="2024-01-02 09:33:00",
        frequency="1m",
        fields=["close", "volume"],
        fq="none",
    )

    assert list(df.columns) == ["close", "volume"]
    assert df.index[0] == pd.Timestamp("2024-01-02 09:31:00")
    assert df.iloc[1]["volume"] == 200.0
    ak = provider._ensure_akshare()
    assert ak.calls[0][0] == "stock_zh_a_hist_min_em"
    assert ak.calls[0][1]["period"] == "1"


@pytest.mark.unit
def test_akshare_multi_security_panel_shape() -> None:
    """多证券 panel=True 应返回 (field, code) MultiIndex。"""
    provider = _provider()

    df = provider.get_price(
        ["000001.XSHE", "600000.XSHG"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        fields=["open", "close"],
        panel=True,
    )

    assert isinstance(df.columns, pd.MultiIndex)
    assert df.columns.names == ["field", "code"]
    assert ("close", "600000.XSHG") in df.columns


@pytest.mark.unit
def test_akshare_panel_false_returns_time_code_long_table() -> None:
    """panel=False 应返回 time/code 长表。"""
    provider = _provider()

    df = provider.get_price(
        ["000001.XSHE", "600000.XSHG"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        fields=["close"],
        panel=False,
    )

    assert list(df.columns) == ["time", "code", "close"]
    assert set(df["code"]) == {"000001.XSHE", "600000.XSHG"}


@pytest.mark.unit
def test_akshare_trade_days_and_trade_day() -> None:
    """交易日应支持区间裁剪、count 和单日查询。"""
    provider = _provider()

    days = provider.get_trade_days(start_date="2024-01-01", end_date="2024-01-31", count=2)

    assert [item.date() for item in days] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert provider.get_trade_day("000001.XSHE", "2024-01-02") == {"000001.XSHE": date(2024, 1, 2)}


@pytest.mark.unit
def test_akshare_all_securities_supports_stock_and_fund() -> None:
    """证券列表应支持股票、ETF 和指数当前快照。"""
    provider = _provider()

    stocks = provider.get_all_securities(types="stock")
    funds = provider.get_all_securities(types=["etf", "index"])

    assert stocks.loc["000001.XSHE", "display_name"] == "平安银行"
    assert stocks.loc["600000.XSHG", "type"] == "stock"
    assert "510300.XSHG" in funds.index
    assert funds.loc["510300.XSHG", "type"] == "fund"
    assert "000300.XSHG" in funds.index


@pytest.mark.unit
def test_akshare_index_stocks_prefers_csindex_and_maps_exchange() -> None:
    """指数成分应优先使用中证接口并正确补市场后缀。"""
    provider = _provider()

    codes = provider.get_index_stocks("000300.XSHG")

    assert codes == ["600000.XSHG", "000001.XSHE"]


@pytest.mark.unit
def test_akshare_index_stocks_falls_back_to_sina() -> None:
    """中证接口失败时应回退新浪指数成分。"""
    fake = FakeAk()

    def _raise(symbol: str) -> pd.DataFrame:
        _ = symbol
        raise RuntimeError("csindex unavailable")

    fake.index_stock_cons_csindex = _raise  # type: ignore[method-assign]
    provider = AkshareProvider({"akshare": fake, "cache_dir": None})

    codes = provider.get_index_stocks("000300.XSHG")

    assert codes == ["600000.XSHG"]


@pytest.mark.unit
def test_akshare_split_dividend_maps_sina_event() -> None:
    """分红事件应转换为 scale_factor/bonus_pre_tax/per_base 结构。"""
    provider = _provider()

    events = provider.get_split_dividend(
        "600000.XSHG", start_date="2024-01-01", end_date="2024-12-31"
    )

    assert len(events) == 1
    assert events[0]["security"] == "600000.XSHG"
    assert events[0]["date"] == date(2024, 6, 20)
    assert events[0]["scale_factor"] == pytest.approx(1.3)
    assert events[0]["bonus_pre_tax"] == pytest.approx(2.5)
    assert events[0]["per_base"] == 10


@pytest.mark.unit
def test_akshare_security_info_reads_individual_info() -> None:
    """证券信息应读取股票简称、行业和上市日期。"""
    provider = _provider()

    info = provider.get_security_info("000001.XSHE")

    assert info["display_name"] == "平安银行"
    assert info["industry"] == "银行"
    assert info["start_date"] == date(1991, 4, 3)
    assert info["type"] == "stock"


@pytest.mark.unit
def test_akshare_current_tick_and_live_current() -> None:
    """实时快照应返回聚宽兼容 tick 字段。"""
    provider = _provider()

    tick = provider.get_current_tick("000001.XSHE")
    live = provider.get_live_current("000001.XSHE")
    as_df = provider.get_current_tick("000001.XSHE", df=True)

    assert isinstance(tick, dict)
    assert tick["last_price"] == pytest.approx(10.5)
    assert tick["volume"] == pytest.approx(1234500.0)
    assert tick["paused"] is False
    assert live == {
        "last_price": 10.5,
        "high_limit": 0.0,
        "low_limit": 0.0,
        "paused": False,
    }
    assert isinstance(as_df, pd.DataFrame)
    assert len(as_df) == 1


@pytest.mark.unit
def test_akshare_index_price_uses_index_endpoint() -> None:
    """指数代码应走指数行情接口。"""
    provider = _provider()

    df = provider.get_price(
        "000300.XSHG",
        start_date="2024-01-01",
        end_date="2024-01-31",
        fields=["close"],
    )

    assert not df.empty
    ak = provider._ensure_akshare()
    assert ak.calls[0][0] == "index_zh_a_hist"


@pytest.mark.unit
def test_akshare_pb_pe_spot_maps_codes_and_numeric_columns() -> None:
    """全市场 PB/PE 快照应以6位代码为索引并转为数值列。"""
    provider = _provider()

    df = provider.get_pb_pe_spot()

    assert list(df.columns) == ["pb", "pe"]
    assert df.index.tolist() == ["000001", "600000", "300750"]
    assert df.loc["000001", "pb"] == 1.2
    assert df.loc["000001", "pe"] == 8.5
    assert df.loc["600000", "pb"] == 0.9
    assert pd.api.types.is_numeric_dtype(df["pb"])
    assert pd.api.types.is_numeric_dtype(df["pe"])


@pytest.mark.unit
def test_akshare_market_pb_percentile_prefers_builtin_quantile() -> None:
    """PB 分位应优先取接口自带的全历史分位。"""
    provider = _provider()

    assert provider.get_market_pb_percentile() == 42.5


@pytest.mark.unit
def test_akshare_market_pb_percentile_falls_back_to_series_rank() -> None:
    """接口分位列为空时应按当前值在历史序列中的位置计算。"""
    fake = FakeAk()
    fake.pb_quantile_nan = True
    provider = AkshareProvider({"akshare": fake, "cache_dir": None})

    # 序列 [2.10, 2.30, 2.20] 中最新 2.20 有 2/3 的历史值不高于它
    assert provider.get_market_pb_percentile() == 66.7


@pytest.mark.unit
def test_akshare_market_pb_series_returns_normalized_columns() -> None:
    """历史 PB 序列通过 provider 暴露为标准日期和数值列。"""
    provider = _provider()

    series = provider.get_market_pb_series()

    assert list(series.columns) == ["date", "middlePB"]
    assert series["date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-31",
        "2024-02-29",
        "2024-03-31",
    ]
    assert series["middlePB"].tolist() == [2.1, 2.3, 2.2]


@pytest.mark.unit
def test_akshare_financial_snapshot_filters_codes_and_normalizes() -> None:
    """财务快照应按代码过滤, 并输出 roe/revenue_growth/industry。"""
    provider = _provider()

    snapshot = provider.get_financial_snapshot(["000001.XSHE", "600000.XSHG"])

    assert set(snapshot) == {"000001", "600000"}
    assert snapshot["000001"]["roe"] == 8.07
    assert snapshot["000001"]["revenue_growth"] == 2.42
    assert snapshot["000001"]["name"] == "平安银行"
    assert snapshot["000001"]["eps"] == 0.5
    assert snapshot["000001"]["bvps"] == 10.0
    assert snapshot["000001"]["industry"] == "银行Ⅱ"


@pytest.mark.unit
def test_akshare_financial_snapshot_skips_blank_industry() -> None:
    """行业缺失时应返回空字符串而不是 None。"""
    fake = FakeAk()
    fake.blank_industry = True
    provider = AkshareProvider({"akshare": fake, "cache_dir": None})

    snapshot = provider.get_financial_snapshot(["000001"])

    assert snapshot["000001"]["industry"] == ""


@pytest.mark.unit
def test_akshare_financial_snapshot_falls_back_to_earlier_period() -> None:
    """最新报告期无数据时应逐级回退到更早的报告期。"""
    fake = FakeAk()
    fake.empty_periods = {"20260930"}
    provider = AkshareProvider({"akshare": fake, "cache_dir": None})

    snapshot = provider.get_financial_snapshot()

    assert set(snapshot) == {"000001", "600000"}
    used = [kwargs.get("date") for name, kwargs in fake.calls if name == "stock_yjbb_em"]
    assert "20260930" in used
    assert "20260630" in used


@pytest.mark.unit
def test_akshare_financial_snapshot_accepts_explicit_period() -> None:
    """显式指定报告期时应只请求该报告期。"""
    provider = _provider()

    snapshot = provider.get_financial_snapshot(date="20260630")

    assert set(snapshot) == {"000001", "600000"}
    ak = provider._ensure_akshare()
    used = [kwargs.get("date") for name, kwargs in ak.calls if name == "stock_yjbb_em"]
    assert used == ["20260630"]
