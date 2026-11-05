"""
作者: BruceLee
文件职责:
    回归验证按市值下单和目标市值下单的股数换算，避免浮点误差导致少卖或少买一手。

主要输入:
    BacktestEngine 与 LiveEngine 的订单数量换算方法、构造的持仓和订单对象。

主要输出:
    pytest 断言结果，确认目标市值清仓和按市值换算不会被 `int(float)` 截断误差污染。

上下游关系:
    上游覆盖 `bullet_trade.core.engine` 与 `bullet_trade.core.live_engine` 的订单数量计算；
    下游保护 C2 等按 `order_target_value` 调仓的策略回测和仿真行为。

关键环境或配置约定:
    测试只使用内存对象，不访问真实行情、券商或数据源。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.live_engine import LiveEngine
from bullet_trade.core.models import Context, Order, OrderStatus, Portfolio, Position


def _target_value_order(security: str, value: float) -> Order:
    """构造目标市值订单。

    Args:
        security: 证券代码。
        value: 目标市值。

    Returns:
        Order: 带 `_is_target_value` 标记的订单对象。
    """

    order = Order(
        order_id="test-target-value",
        security=security,
        amount=0,
        status=OrderStatus.open,
        add_time=datetime(2026, 1, 1, 14, 50),
        is_buy=True,
    )
    order._is_target_value = True  # type: ignore[attr-defined]
    order._target_value = value  # type: ignore[attr-defined]
    return order


def _value_order(security: str, value: float, is_buy: bool) -> Order:
    """构造按市值买卖订单。

    Args:
        security: 证券代码。
        value: 买卖市值。
        is_buy: True 表示买入，False 表示卖出。

    Returns:
        Order: 带 `_target_value` 标记的订单对象。
    """

    order = Order(
        order_id="test-value",
        security=security,
        amount=0,
        status=OrderStatus.open,
        add_time=datetime(2026, 1, 1, 14, 50),
        is_buy=is_buy,
    )
    order._target_value = value  # type: ignore[attr-defined]
    return order


def test_backtest_order_target_value_zero_sells_all_when_float_is_near_integer() -> None:
    """目标市值清零时应按当前持仓股数全卖，不能因浮点误差残留 100 股。

    Args:
        无。

    Returns:
        None。
    """

    engine = BacktestEngine()
    position = Position(
        security="513100.XSHG",
        total_amount=113700,
        closeable_amount=113700,
        avg_cost=1.471,
        price=1.446,
    )
    engine.context = Context(
        portfolio=Portfolio(positions={"513100.XSHG": position}),
        current_dt=datetime(2015, 6, 9, 14, 50),
    )

    amount = engine._calculate_order_amount(_target_value_order("513100.XSHG", 0.0), 1.446)

    assert amount == -113700


def test_backtest_value_order_uses_near_integer_amount_without_truncation() -> None:
    """按市值卖出遇到贴近整数的浮点结果时应得到完整股数。

    Args:
        无。

    Returns:
        None。
    """

    engine = BacktestEngine()
    engine.context = Context(portfolio=Portfolio(), current_dt=datetime(2026, 1, 1, 14, 50))

    amount = engine._calculate_order_amount(
        _value_order("513100.XSHG", 113700 * 1.446, is_buy=False),
        1.446,
    )

    assert amount == -113700


def test_live_order_target_value_zero_sells_all_when_float_is_near_integer() -> None:
    """LiveEngine 目标市值清零时也应按当前持仓全卖。

    Args:
        无。

    Returns:
        None。
    """

    engine = LiveEngine(strategy_file=Path(__file__))
    engine._portfolio.positions["513100.XSHG"] = Position(
        security="513100.XSHG",
        total_amount=113700,
        closeable_amount=113700,
        avg_cost=1.471,
        price=1.446,
    )

    amount, is_buy = engine._resolve_order_amount(
        _target_value_order("513100.XSHG", 0.0),
        1.446,
    )

    assert amount == 113700
    assert is_buy is False
