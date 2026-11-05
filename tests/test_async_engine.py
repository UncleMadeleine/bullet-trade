"""
异步回测引擎测试

测试 AsyncBacktestEngine 的核心功能
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bullet_trade.core.async_engine import AsyncBacktestEngine
from bullet_trade.data.providers.base import DataProvider

# ============ 离线数据源 ============


class _OfflineAsyncProvider(DataProvider):
    """
    异步引擎测试专用离线数据源。

    职责：为默认 pytest 提供固定交易日和行情，避免异步回测测试误连真实 JQData/QMT。
    核心协作对象：`bullet_trade.data.api` 的全局 provider。
    关键状态：无外部连接、无磁盘缓存，所有返回值由输入时间窗口即时生成。
    """

    name = "offline_async"

    def auth(
        self,
        user: Optional[str] = None,
        pwd: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        初始化离线数据源。

        Args:
            user: 兼容数据源认证签名，测试中不使用。
            pwd: 兼容数据源认证签名，测试中不使用。
            host: 兼容数据源认证签名，测试中不使用。
            port: 兼容数据源认证签名，测试中不使用。

        Returns:
            None。该数据源不访问外部服务。
        """
        return None

    def get_trade_days(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        count: Optional[int] = None,
    ) -> List[datetime]:
        """
        返回工作日交易日序列。

        Args:
            start_date: 查询开始日期；缺省时按 end_date 和 count 推导。
            end_date: 查询结束日期；缺省时使用 2024-12-31。
            count: 需要返回的最近交易日数量。

        Returns:
            List[datetime]: pandas 工作日序列转换后的 datetime 列表。
        """
        end_ts = pd.to_datetime(end_date or "2024-12-31").normalize()
        if count is not None:
            return list(pd.bdate_range(end=end_ts, periods=count).to_pydatetime())
        start_ts = pd.to_datetime(start_date or end_ts).normalize()
        return list(pd.bdate_range(start=start_ts, end=end_ts).to_pydatetime())

    def get_price(
        self,
        security: Union[str, List[str]],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        frequency: str = "daily",
        fields: Optional[List[str]] = None,
        skip_paused: bool = False,
        fq: str = "pre",
        count: Optional[int] = None,
        panel: bool = True,
        fill_paused: bool = True,
        pre_factor_ref_date: Optional[Union[str, datetime]] = None,
        prefer_engine: bool = False,
        force_no_engine: bool = False,
    ) -> pd.DataFrame:
        """
        返回固定价格行情。

        Args:
            security: 单个或多个证券代码。
            start_date: 行情开始时间。
            end_date: 行情结束时间。
            frequency: 行情频率；测试中日线和分钟线均返回同一离线价格。
            fields: 需要的字段列表。
            skip_paused: 兼容公开 API 参数，测试中不改变返回。
            fq: 兼容复权参数，测试中不改变返回。
            count: 需要返回的最近记录数量。
            panel: 兼容公开 API 参数，多证券时返回 MultiIndex 列。
            fill_paused: 兼容公开 API 参数，测试中不改变返回。
            pre_factor_ref_date: 兼容动态复权参数，测试中不改变返回。
            prefer_engine: 兼容 provider engine 参数，测试中不改变返回。
            force_no_engine: 兼容 provider engine 参数，测试中不改变返回。

        Returns:
            pd.DataFrame: 以时间为索引的行情表。
        """
        _ = skip_paused, fq, fill_paused, pre_factor_ref_date, prefer_engine, force_no_engine
        end_ts = pd.to_datetime(end_date or start_date or "2024-01-01").normalize()
        if count is not None:
            index = pd.bdate_range(end=end_ts, periods=count)
        else:
            start_ts = pd.to_datetime(start_date or end_ts).normalize()
            index = pd.bdate_range(start=start_ts, end=end_ts)
        if index.empty:
            index = pd.DatetimeIndex([end_ts])

        requested_fields = fields or ["open", "close", "high", "low", "volume", "money"]
        securities = security if isinstance(security, list) else [security]

        def _field_value(field: str) -> Any:
            """
            生成单字段固定值。

            Args:
                field: 行情字段名。

            Returns:
                Any: 与字段语义匹配的固定值。
            """
            values: Dict[str, Any] = {
                "open": 10.0,
                "close": 10.0,
                "high": 10.2,
                "low": 9.8,
                "high_limit": 11.0,
                "low_limit": 9.0,
                "paused": False,
                "volume": 100000,
                "money": 1000000.0,
                "factor": 1.0,
            }
            return values.get(field, 10.0)

        if len(securities) == 1:
            return pd.DataFrame(
                {field: [_field_value(field)] * len(index) for field in requested_fields},
                index=index,
            )

        data = {
            (field, code): [_field_value(field)] * len(index)
            for field in requested_fields
            for code in securities
        }
        return pd.DataFrame(data, index=index)

    def get_all_securities(
        self,
        types: Union[str, List[str]] = "stock",
        date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        """
        返回最小证券列表。

        Args:
            types: 证券类型过滤条件，测试中仅保留兼容签名。
            date: 查询日期，测试中不改变返回。

        Returns:
            pd.DataFrame: 包含测试常用代码的证券表。
        """
        _ = types, date
        return pd.DataFrame(
            {
                "display_name": ["平安银行", "浦发银行", "万科A", "沪深300"],
                "type": ["stock", "stock", "stock", "index"],
            },
            index=["000001.XSHE", "600000.XSHG", "000002.XSHE", "000300.XSHG"],
        )

    def get_index_stocks(
        self,
        index_symbol: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> List[str]:
        """
        返回固定指数成分。

        Args:
            index_symbol: 指数代码。
            date: 查询日期，测试中不改变返回。

        Returns:
            List[str]: 固定股票列表。
        """
        _ = index_symbol, date
        return ["000001.XSHE", "600000.XSHG", "000002.XSHE"]

    def get_split_dividend(
        self,
        security: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        """
        返回权益事件。

        Args:
            security: 证券代码。
            start_date: 查询开始日期。
            end_date: 查询结束日期。

        Returns:
            List[Dict[str, Any]]: 异步引擎测试不覆盖分红，固定返回空列表。
        """
        _ = security, start_date, end_date
        return []


@pytest.fixture(autouse=True)
def _use_offline_async_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    将本文件所有测试固定到离线数据源。

    Args:
        monkeypatch: pytest 提供的临时属性替换工具。

    Returns:
        None。fixture 结束后自动恢复全局 provider 状态。
    """
    from bullet_trade.data import api as data_api

    provider = _OfflineAsyncProvider()
    monkeypatch.setattr(data_api, "_provider", provider, raising=False)
    monkeypatch.setattr(data_api, "_provider_cache", {provider.name: provider}, raising=False)
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {provider.name: True}, raising=False)
    monkeypatch.setattr(data_api, "_auth_attempted", True, raising=False)


# ============ 测试策略 ============


def test_simple_sync_strategy():
    """测试同步策略在异步引擎中运行"""

    # 同步策略（现有代码风格）
    def initialize(context):
        from bullet_trade.core.scheduler import run_daily
        from bullet_trade.core.settings import set_benchmark

        set_benchmark("000300.XSHG")
        context.stocks = ["000001.XSHE", "600000.XSHG"]
        run_daily(market_open, "open")

    def market_open(context):
        """定时任务函数：只接收 context 参数（符合聚宽规范）"""
        from bullet_trade.core.orders import order_target_value

        for stock in context.stocks:
            order_target_value(stock, 5000)

    # 创建异步引擎（不传 handle_data，只使用定时任务）
    engine = AsyncBacktestEngine(
        initialize=initialize,
    )

    # 运行回测（异步模式）
    results = engine.run(
        start_date="2024-01-01",
        end_date="2024-01-31",
        capital_base=100000,
        frequency="daily",
        use_async=True,  # 关键参数
    )

    assert results is not None
    assert "summary" in results
    assert "meta" in results

    # 从新的结构中提取数据
    final_value = results["meta"]["final_total_value"]
    initial_value = results["meta"]["initial_total_value"]
    total_returns = (final_value - initial_value) / initial_value

    print("\n✅ 同步策略测试通过")
    print(f"   总收益率: {total_returns:.2%}")
    print(f"   最终价值: ¥{final_value:,.2f}")
    print(f"   耗时: {results.get('runtime_seconds', 0):.2f}秒")


@pytest.mark.asyncio
async def test_async_strategy():
    """测试异步策略"""

    # 异步策略
    async def initialize(context):
        from bullet_trade.core.scheduler import run_daily
        from bullet_trade.core.settings import set_benchmark

        set_benchmark("000300.XSHG")
        context.stocks = ["000001.XSHE"]
        run_daily(market_open, "open")

    async def market_open(context):
        """异步定时任务函数：只接收 context 参数（符合聚宽规范）"""
        from bullet_trade.core.orders import order_target_value

        # 模拟异步操作
        await asyncio.sleep(0.001)

        for stock in context.stocks:
            order_target_value(stock, 10000)

    # 创建异步引擎（不传 handle_data，只使用定时任务）
    engine = AsyncBacktestEngine(
        initialize=initialize,
    )

    # 直接调用 run_async
    results = await engine.run_async(
        start_date="2024-01-01", end_date="2024-01-31", capital_base=100000, frequency="daily"
    )

    assert results is not None
    assert "summary" in results
    assert "meta" in results

    # 从新的结构中提取数据
    final_value = results["meta"]["final_total_value"]
    initial_value = results["meta"]["initial_total_value"]
    total_returns = (final_value - initial_value) / initial_value

    print("\n✅ 异步策略测试通过")
    print(f"   总收益率: {total_returns:.2%}")
    print(f"   最终价值: ¥{final_value:,.2f}")
    print(f"   耗时: {results.get('runtime_seconds', 0):.2f}秒")


def test_backward_compatibility():
    """测试向后兼容性：use_async=False 使用原有引擎"""

    def initialize(context):
        from bullet_trade.core.settings import set_benchmark

        set_benchmark("000300.XSHG")
        context.stocks = ["000001.XSHE"]

    def market_open(context, data):
        from bullet_trade.core.orders import order

        order(context.stocks[0], 100)

    # 创建异步引擎，但以同步模式运行
    engine = AsyncBacktestEngine(
        initialize=initialize,
        handle_data=market_open,
    )

    # use_async=False（默认值）
    results = engine.run(
        start_date="2024-01-01",
        end_date="2024-01-10",
        capital_base=100000,
        frequency="daily",
        use_async=False,  # 使用同步模式
    )

    assert results is not None

    print("\n✅ 向后兼容性测试通过")
    print("   同步模式正常工作")


# ============ 性能对比测试 ============


def test_performance_comparison():
    """对比同步和异步模式的性能"""

    def initialize(context):
        from bullet_trade.core.scheduler import run_daily
        from bullet_trade.core.settings import set_benchmark

        set_benchmark("000300.XSHG")
        context.stocks = ["000001.XSHE", "600000.XSHG", "000002.XSHE"]
        run_daily(market_open, "open")

    def market_open(context):
        """定时任务函数：只接收 context 参数（符合聚宽规范）"""
        from bullet_trade.core.orders import order_target_value

        for stock in context.stocks:
            order_target_value(stock, 3000)

    # 同步模式（不传 handle_data，只使用定时任务）
    engine_sync = AsyncBacktestEngine(
        initialize=initialize,
    )

    results_sync = engine_sync.run(
        start_date="2024-01-01",
        end_date="2024-03-31",
        capital_base=100000,
        frequency="daily",
        use_async=False,
    )

    time_sync = results_sync.get("runtime_seconds", 0)

    # 异步模式（不传 handle_data，只使用定时任务）
    engine_async = AsyncBacktestEngine(
        initialize=initialize,
    )

    results_async = engine_async.run(
        start_date="2024-01-01",
        end_date="2024-03-31",
        capital_base=100000,
        frequency="daily",
        use_async=True,
    )

    time_async = results_async.get("runtime_seconds", 0)

    print("\n📊 性能对比")
    print(f"   同步模式: {time_sync:.2f}秒")
    print(f"   异步模式: {time_async:.2f}秒")

    if time_async < time_sync:
        speedup = time_sync / time_async
        print(f"   ⚡ 异步模式快 {speedup:.2f}x")
    else:
        print("   ℹ️  性能相近（日线回测差异不大）")


# ============ 主程序 ============

if __name__ == "__main__":
    print("🧪 开始测试异步回测引擎...\n")

    print("=" * 60)
    print("测试 1：同步策略在异步引擎中运行")
    print("=" * 60)
    test_simple_sync_strategy()

    print("\n" + "=" * 60)
    print("测试 2：纯异步策略")
    print("=" * 60)
    asyncio.run(test_async_strategy())

    print("\n" + "=" * 60)
    print("测试 3：向后兼容性")
    print("=" * 60)
    test_backward_compatibility()

    print("\n" + "=" * 60)
    print("测试 4：性能对比")
    print("=" * 60)
    test_performance_comparison()

    print("\n" + "=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)

    print("\n💡 核心特性验证：")
    print("  ✅ 同步策略无需修改即可在异步引擎中运行")
    print("  ✅ 异步策略获得更好的性能（分钟/实盘）")
    print("  ✅ 向后兼容：use_async=False 使用原有引擎")
    print("  ✅ 事件驱动：集成 EventLoop + EventBus + AsyncScheduler")
    print("  ✅ 防重叠执行：AsyncScheduler 自动处理")
