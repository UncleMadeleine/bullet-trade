"""
测试 every_bar 在回测下的行为

测试目标：
1. every_bar 在分钟回测下按每分钟触发
2. every_bar 在日回测下也按每分钟触发，保持回测与实盘一致
3. every_bar 与 every_minute 等价
4. 分钟边界验证（09:31、11:30、13:01、15:00）
5. 周期触发验证（周三 10:00、月首 10:00）
"""
import datetime as dt
from datetime import time
from typing import List, Optional

import pytest

from bullet_trade.core.scheduler import (
    TimeExpression,
    generate_daily_schedule,
    get_market_periods,
    run_daily,
    run_monthly,
    run_weekly,
    get_trade_calendar,
    set_trade_calendar,
    unschedule_all,
)
from bullet_trade.core.settings import get_settings, set_option


@pytest.fixture(autouse=True)
def reset_scheduler_and_settings():
    """每个测试前后重置调度器和设置"""
    unschedule_all()
    set_trade_calendar([], dt.date.today())
    original_frequency = get_settings().options.get('backtest_frequency', 'day')
    yield
    unschedule_all()
    set_trade_calendar([], dt.date.today())
    set_option('backtest_frequency', original_frequency)


def _build_schedule(
    day: dt.datetime,
    calendar_days: Optional[List[dt.date]] = None,
    start_date: Optional[dt.date] = None,
):
    """构建指定日期的调度表"""
    periods = get_market_periods()
    calendar_days = calendar_days or [day.date()]
    start = start_date or calendar_days[0]
    set_trade_calendar(calendar_days, start)
    return generate_daily_schedule(day, get_trade_calendar(), lambda _ref=None: periods)


class TestEveryBarMinuteFrequency:
    """测试 every_bar 在分钟回测下的行为"""
    
    def test_every_bar_resolves_to_all_minutes_in_minute_frequency(self):
        """every_bar 在分钟回测下解析为所有交易分钟"""
        # 设置分钟回测频率
        set_option('backtest_frequency', 'minute')
        
        # 注册 every_bar 任务
        run_daily(lambda ctx: None, 'every_bar')
        
        # 生成某交易日的调度表
        trade_day = dt.datetime(2025, 6, 2)  # 周一
        schedule = _build_schedule(trade_day)
        
        # 提取 every_bar 任务的触发时间
        every_bar_times = [
            dt for dt, tasks in schedule.items()
            if any(task.time == 'every_bar' for task in tasks)
        ]
        
        # 验证：至少包含所有交易时段的分钟数
        # A股交易时段：09:30-11:29 (120分钟), 13:00-14:59 (120分钟)
        assert len(every_bar_times) == 240  # 120 + 120
        
        # 验证首尾分钟
        assert every_bar_times[0].time() == time(9, 30)
        assert every_bar_times[-1].time() == time(14, 59)
    
    def test_every_bar_minute_boundaries(self):
        """验证 every_bar 覆盖关键分钟边界"""
        set_option('backtest_frequency', 'minute')
        run_daily(lambda ctx: None, 'every_bar')
        
        trade_day = dt.datetime(2025, 6, 2)
        schedule = _build_schedule(trade_day)
        
        # 关键分钟边界
        boundaries = [
            dt.datetime(2025, 6, 2, 9, 30),   # 开盘第一分钟（注意是09:30）
            dt.datetime(2025, 6, 2, 9, 31),   # 开盘后第二分钟
            dt.datetime(2025, 6, 2, 11, 29),  # 上午最后一分钟
            dt.datetime(2025, 6, 2, 13, 0),   # 下午开盘第一分钟（注意是13:00）
            dt.datetime(2025, 6, 2, 13, 1),   # 下午开盘后第二分钟
            dt.datetime(2025, 6, 2, 14, 59),  # 收盘
        ]
        
        for boundary in boundaries:
            assert boundary in schedule, f"边界时间 {boundary} 应该在调度表中"
    
    @pytest.mark.parametrize('frequency', ['minute', 'day', 'daily', '1d'])
    def test_every_bar_equals_every_minute(self, frequency):
        """every_bar 与 every_minute 在常见回测频率写法下等价"""
        set_option('backtest_frequency', frequency)
        
        # 注册两个任务
        run_daily(lambda ctx: None, 'every_bar')
        run_daily(lambda ctx: None, 'every_minute')
        
        trade_day = dt.datetime(2025, 6, 2)
        schedule = _build_schedule(trade_day)
        
        # 提取各自的触发时间
        every_bar_times = {
            dt for dt, tasks in schedule.items()
            if any(task.time == 'every_bar' for task in tasks)
        }
        every_minute_times = {
            dt for dt, tasks in schedule.items()
            if any(task.time == 'every_minute' for task in tasks)
        }
        
        # 验证：两者时间点集合完全相同
        assert every_bar_times == every_minute_times


class TestEveryBarDayFrequency:
    """测试 every_bar 在日回测下的行为"""
    
    def test_every_bar_triggers_every_minute_in_day_frequency(self):
        """every_bar 在日回测下也按交易分钟触发"""
        # 设置日回测频率
        set_option('backtest_frequency', 'day')
        
        run_daily(lambda ctx: None, 'every_bar')
        
        trade_day = dt.datetime(2025, 6, 2)
        schedule = _build_schedule(trade_day)
        
        # 提取 every_bar 任务的触发时间
        every_bar_times = [
            dt for dt, tasks in schedule.items()
            if any(task.time == 'every_bar' for task in tasks)
        ]
        
        # 验证：日频回测下仍与实盘 every_bar 语义一致，按交易分钟触发
        assert len(every_bar_times) == 240
        assert every_bar_times[0] == dt.datetime(2025, 6, 2, 9, 30)
        assert every_bar_times[-1] == dt.datetime(2025, 6, 2, 14, 59)


class TestPeriodicTriggers:
    """测试周期性触发（周、月）"""
    
    def test_weekly_wednesday_10am_trigger(self):
        """周三 10:00 定时触发"""
        set_option('backtest_frequency', 'minute')
        
        # 注册周三 10:00 任务
        run_weekly(lambda ctx: None, weekday=3, time='10:00')  # 当周第 3 个交易日
        calendar_days = [
            dt.date(2025, 6, 2),
            dt.date(2025, 6, 3),
            dt.date(2025, 6, 4),
            dt.date(2025, 6, 5),
            dt.date(2025, 6, 6),
        ]
        
        # 测试几个不同的日期
        wednesday = dt.datetime(2025, 6, 4)  # 2025-06-04 是周三
        tuesday = dt.datetime(2025, 6, 3)    # 2025-06-03 是周二
        
        schedule_wed = _build_schedule(wednesday, calendar_days)
        schedule_tue = _build_schedule(tuesday, calendar_days)
        
        expected_wed = dt.datetime(2025, 6, 4, 10, 0)
        expected_tue = dt.datetime(2025, 6, 3, 10, 0)
        
        # 周三应该触发
        assert expected_wed in schedule_wed
        # 周二不应该触发
        assert expected_tue not in schedule_tue
    
    def test_monthly_first_trading_day_11am_trigger(self):
        """每月首个交易日 11:00 触发"""
        set_option('backtest_frequency', 'minute')
        
        # 注册每月 1 号 11:00 任务
        run_monthly(lambda ctx: None, monthday=1, time='11:00')
        calendar_days = [
            dt.date(2025, 6, 2),
            dt.date(2025, 6, 3),
            dt.date(2025, 7, 1),
            dt.date(2025, 7, 2),
        ]
        
        # 测试 2025 年 6 月和 7 月的首个交易日
        # 假设 6月1日（周日）顺延到 6月2日（周一）
        june_first_trade_day = dt.datetime(2025, 6, 2)  # 周一
        june_second_day = dt.datetime(2025, 6, 3)       # 周二
        july_first_trade_day = dt.datetime(2025, 7, 1)
        
        # 第一次调用：6月2日触发
        schedule_june_2 = _build_schedule(june_first_trade_day, calendar_days)
        expected_june_2 = dt.datetime(2025, 6, 2, 11, 0)
        assert expected_june_2 in schedule_june_2
        
        # 第二次调用：6月3日不应触发（因为已经在6月2日触发过）
        schedule_june_3 = _build_schedule(june_second_day, calendar_days)
        expected_june_3 = dt.datetime(2025, 6, 3, 11, 0)
        assert expected_june_3 not in schedule_june_3
        schedule_july_1 = _build_schedule(july_first_trade_day, calendar_days, start_date=calendar_days[0])
        expected_july_1 = dt.datetime(2025, 7, 1, 11, 0)
        assert expected_july_1 in schedule_july_1


class TestTimeExpressionResolve:
    """直接测试 TimeExpression.resolve 方法"""
    
    def test_every_bar_resolve_with_minute_frequency(self):
        """测试 every_bar 在分钟频率下的 resolve 行为"""
        set_option('backtest_frequency', 'minute')
        
        expr = TimeExpression.parse('every_bar', {})
        trade_day = dt.datetime(2025, 6, 2)
        periods = get_market_periods()
        
        times = expr.resolve(trade_day, periods)
        
        # 应该返回所有交易分钟
        assert len(times) == 240
        assert times[0] == dt.datetime(2025, 6, 2, 9, 30)
        assert times[-1] == dt.datetime(2025, 6, 2, 14, 59)
    
    def test_every_bar_resolve_with_day_frequency(self):
        """测试 every_bar 在日频率下的 resolve 行为"""
        set_option('backtest_frequency', 'day')
        
        expr = TimeExpression.parse('every_bar', {})
        trade_day = dt.datetime(2025, 6, 2)
        periods = get_market_periods()
        
        times = expr.resolve(trade_day, periods)
        
        # 应该返回所有交易分钟，与实盘 every_bar 语义一致
        assert len(times) == 240
        assert times[0] == dt.datetime(2025, 6, 2, 9, 30)
        assert times[-1] == dt.datetime(2025, 6, 2, 14, 59)
    
    def test_every_minute_always_returns_all_minutes(self):
        """every_minute 应该总是返回所有分钟，不受频率影响"""
        expr = TimeExpression.parse('every_minute', {})
        trade_day = dt.datetime(2025, 6, 2)
        periods = get_market_periods()
        
        # 测试日频率
        set_option('backtest_frequency', 'day')
        times_day = expr.resolve(trade_day, periods)
        
        # 测试分钟频率
        set_option('backtest_frequency', 'minute')
        times_minute = expr.resolve(trade_day, periods)
        
        # 两者应该相同，都返回所有分钟
        assert len(times_day) == 240
        assert len(times_minute) == 240
        assert times_day == times_minute
