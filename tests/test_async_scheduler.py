"""
异步调度器测试

测试 AsyncScheduler 的核心功能，特别是防重叠执行机制
"""

import asyncio
import logging
import pytest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bullet_trade.core.async_scheduler import (
    AsyncScheduler,
    AsyncScheduleTask,
    ScheduleType,
    OverlapStrategy,
    get_scheduler,
    reset_scheduler,
)
from bullet_trade.core.scheduler import get_trade_calendar, set_trade_calendar


# ============ 基础功能测试 ============

@pytest.fixture(autouse=True)
def reset_trade_calendar():
    set_trade_calendar([], datetime.now().date())
    yield
    set_trade_calendar([], datetime.now().date())

def test_scheduler_creation():
    """测试调度器创建"""
    scheduler = AsyncScheduler()
    assert len(scheduler.get_all_tasks()) == 0
    print("✅ 调度器创建测试通过")


def test_register_task_log_is_user_facing(caplog):
    """注册日志应只说明定时任务存在，不暴露重叠处理细节。"""
    caplog.set_level(logging.INFO, logger="jq_strategy")
    scheduler = AsyncScheduler()

    def task(_context):
        pass

    scheduler.run_daily(task, '09:00', OverlapStrategy.SKIP)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "已注册定时任务" in messages
    assert "每个交易日 09:00" in messages
    assert "重叠处理" not in messages
    assert "跳过" not in messages


@pytest.mark.asyncio
async def test_run_daily():
    """测试每日任务"""
    scheduler = AsyncScheduler()
    
    results = []
    
    async def daily_task(value):
        results.append(value)
    
    # 注册任务
    task_id = scheduler.run_daily(daily_task, '09:30')
    assert task_id in scheduler._task_map
    
    # 触发任务
    test_time = datetime(2024, 1, 15, 9, 30)
    await scheduler.trigger(test_time, "test")
    
    assert results == ["test"]
    print("✅ 每日任务测试通过")


@pytest.mark.asyncio
async def test_run_weekly():
    """测试每周任务"""
    scheduler = AsyncScheduler()
    
    results = []
    
    def weekly_task(value):
        results.append(value)
    
    # 注册任务（当周第 1 个交易日）
    scheduler.run_weekly(weekly_task, 1, '10:00')
    calendar_days = [
        datetime(2024, 1, 15).date(),
        datetime(2024, 1, 16).date(),
        datetime(2024, 1, 17).date(),
    ]
    set_trade_calendar(calendar_days, calendar_days[0])
    scheduler.set_trade_calendar(get_trade_calendar())
    
    # 周一应该执行
    monday = datetime(2024, 1, 15, 10, 0)  # 2024-01-15 是周一
    await scheduler.trigger(monday, "monday")
    assert results == ["monday"]
    
    # 周二不应该执行
    tuesday = datetime(2024, 1, 16, 10, 0)
    await scheduler.trigger(tuesday, "tuesday")
    assert results == ["monday"]  # 没有变化
    
    print("✅ 每周任务测试通过")


@pytest.mark.asyncio
async def test_run_monthly():
    """测试每月任务"""
    scheduler = AsyncScheduler()
    
    results = []
    
    def monthly_task(value):
        results.append(value)
    
    # 注册任务（每月1号）
    scheduler.run_monthly(monthly_task, 1, '15:00')
    calendar_days = [
        datetime(2024, 1, 1).date(),
        datetime(2024, 1, 2).date(),
        datetime(2024, 1, 3).date(),
    ]
    set_trade_calendar(calendar_days, calendar_days[0])
    scheduler.set_trade_calendar(get_trade_calendar())
    
    # 1号应该执行
    first_day = datetime(2024, 1, 1, 15, 0)
    await scheduler.trigger(first_day, "first")
    assert results == ["first"]
    
    # 2号不应该执行
    second_day = datetime(2024, 1, 2, 15, 0)
    await scheduler.trigger(second_day, "second")
    assert results == ["first"]  # 没有变化
    
    print("✅ 每月任务测试通过")


# ============ 重叠执行策略测试 ============

@pytest.mark.asyncio
async def test_overlap_skip():
    """测试重叠跳过策略"""
    scheduler = AsyncScheduler()
    
    results = []
    
    async def slow_task(value):
        results.append(f"start_{value}")
        await asyncio.sleep(0.1)  # 模拟耗时操作
        results.append(f"end_{value}")
    
    # 注册任务（默认策略：SKIP）
    scheduler.run_daily(slow_task, '09:30', OverlapStrategy.SKIP)
    
    # 第一次调用
    test_time = datetime(2024, 1, 15, 9, 30)
    task1 = asyncio.create_task(scheduler.trigger(test_time, "1"))
    
    # 等待一小段时间（任务还在执行）
    await asyncio.sleep(0.05)
    
    # 第二次调用（应该被跳过）
    task2 = asyncio.create_task(scheduler.trigger(test_time, "2"))
    
    # 等待所有任务完成
    await task1
    await task2
    
    # 第二次调用应该被跳过
    assert "start_1" in results
    assert "end_1" in results
    assert "start_2" not in results  # 被跳过了
    
    print("✅ 重叠跳过策略测试通过")
    print(f"   执行结果: {results}")


@pytest.mark.asyncio
async def test_overlap_wait():
    """测试重叠等待策略"""
    scheduler = AsyncScheduler()
    
    results = []
    
    async def slow_task(value):
        results.append(f"start_{value}")
        await asyncio.sleep(0.1)
        results.append(f"end_{value}")
    
    # 注册任务（等待策略）
    scheduler.run_daily(slow_task, '09:30', OverlapStrategy.WAIT)
    
    # 第一次调用
    test_time = datetime(2024, 1, 15, 9, 30)
    task1 = asyncio.create_task(scheduler.trigger(test_time, "1"))
    
    # 等待一小段时间
    await asyncio.sleep(0.05)
    
    # 第二次调用（会等待第一次完成）
    task2 = asyncio.create_task(scheduler.trigger(test_time, "2"))
    
    # 等待所有任务完成
    await task1
    await task2
    
    # 两次调用都应该执行，且顺序正确
    assert results == ["start_1", "end_1", "start_2", "end_2"]
    
    print("✅ 重叠等待策略测试通过")
    print(f"   执行结果: {results}")


@pytest.mark.asyncio
async def test_overlap_concurrent():
    """测试重叠并发策略"""
    scheduler = AsyncScheduler()
    
    results = []
    
    async def slow_task(value):
        results.append(f"start_{value}")
        await asyncio.sleep(0.1)
        results.append(f"end_{value}")
    
    # 注册任务（并发策略）
    scheduler.run_daily(slow_task, '09:30', OverlapStrategy.CONCURRENT)
    
    # 第一次调用
    test_time = datetime(2024, 1, 15, 9, 30)
    task1 = asyncio.create_task(scheduler.trigger(test_time, "1"))
    
    # 立即第二次调用（会并发执行）
    task2 = asyncio.create_task(scheduler.trigger(test_time, "2"))
    
    # 等待所有任务完成
    await task1
    await task2
    
    # 两次调用都应该执行，但顺序可能交叉
    assert "start_1" in results
    assert "start_2" in results
    assert "end_1" in results
    assert "end_2" in results
    
    print("✅ 重叠并发策略测试通过")
    print(f"   执行结果: {results}")


# ============ 任务管理测试 ============

@pytest.mark.asyncio
async def test_unschedule():
    """测试取消任务"""
    scheduler = AsyncScheduler()
    
    results = []
    
    def task(value):
        results.append(value)
    
    # 注册任务
    task_id = scheduler.run_daily(task, '09:30')
    assert len(scheduler.get_all_tasks()) == 1
    
    # 取消任务
    scheduler.unschedule(task_id)
    assert len(scheduler.get_all_tasks()) == 0
    
    # 触发不应该执行
    test_time = datetime(2024, 1, 15, 9, 30)
    await scheduler.trigger(test_time, "test")
    assert results == []
    
    print("✅ 取消任务测试通过")


@pytest.mark.asyncio
async def test_enable_disable():
    """测试启用/禁用任务"""
    scheduler = AsyncScheduler()
    
    results = []
    
    def task(value):
        results.append(value)
    
    # 注册任务
    task_id = scheduler.run_daily(task, '09:30')
    test_time = datetime(2024, 1, 15, 9, 30)
    
    # 默认启用，应该执行
    await scheduler.trigger(test_time, "enabled")
    assert results == ["enabled"]
    
    # 禁用任务
    scheduler.disable_task(task_id)
    await scheduler.trigger(test_time, "disabled")
    assert results == ["enabled"]  # 没有变化
    
    # 重新启用
    scheduler.enable_task(task_id)
    await scheduler.trigger(test_time, "re-enabled")
    assert results == ["enabled", "re-enabled"]
    
    print("✅ 启用/禁用任务测试通过")


# ============ 同步异步混合测试 ============

@pytest.mark.asyncio
async def test_sync_async_tasks():
    """测试同步和异步任务混合"""
    scheduler = AsyncScheduler()
    
    results = []
    
    # 同步任务
    def sync_task(value):
        results.append(f"sync_{value}")
    
    # 异步任务
    async def async_task(value):
        await asyncio.sleep(0.01)
        results.append(f"async_{value}")
    
    # 注册两种任务
    scheduler.run_daily(sync_task, '09:30')
    scheduler.run_daily(async_task, '09:30')
    
    # 触发执行
    test_time = datetime(2024, 1, 15, 9, 30)
    await scheduler.trigger(test_time, "test")
    
    # 两种任务都应该执行
    assert "sync_test" in results
    assert "async_test" in results
    
    print("✅ 同步异步混合测试通过")


# ============ 统计信息测试 ============

@pytest.mark.asyncio
async def test_stats():
    """测试统计信息"""
    scheduler = AsyncScheduler()
    
    def task1():
        pass
    
    async def task2():
        pass
    
    # 注册任务
    scheduler.run_daily(task1, '09:30')
    scheduler.run_daily(task2, '10:00')
    
    # 获取统计
    stats = scheduler.get_stats()
    assert stats['total_tasks'] == 2
    assert stats['enabled_tasks'] == 2
    assert stats['running_tasks'] == 0
    
    print("✅ 统计信息测试通过")
    print(f"   统计: {stats}")


# ============ 主程序 ============

if __name__ == "__main__":
    print("🧪 开始测试异步调度器...\n")
    
    # 运行测试
    test_scheduler_creation()
    
    asyncio.run(test_run_daily())
    asyncio.run(test_run_weekly())
    asyncio.run(test_run_monthly())
    
    print("\n" + "="*60)
    print("重叠执行策略测试")
    print("="*60)
    
    asyncio.run(test_overlap_skip())
    asyncio.run(test_overlap_wait())
    asyncio.run(test_overlap_concurrent())
    
    print("\n" + "="*60)
    print("任务管理测试")
    print("="*60)
    
    asyncio.run(test_unschedule())
    asyncio.run(test_enable_disable())
    
    print("\n" + "="*60)
    print("其他测试")
    print("="*60)
    
    asyncio.run(test_sync_async_tasks())
    asyncio.run(test_stats())
    
    print("\n" + "="*60)
    print("🎉 所有测试通过！")
    print("="*60)
    
    print("\n💡 核心特性验证：")
    print("  ✅ SKIP 策略：任务重叠时跳过，避免竞态")
    print("  ✅ WAIT 策略：任务重叠时等待，保证顺序")
    print("  ✅ CONCURRENT 策略：允许并发，需自行处理竞态")
    print("  ✅ 同步异步混合：引擎自动适配")
    print("  ✅ 任务管理：注册/取消/启用/禁用")
