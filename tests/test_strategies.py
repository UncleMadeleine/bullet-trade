"""
策略测试运行器

自动发现并测试 tests/strategies/ 目录下的所有策略文件
配置文件：tests/strategies/config.yaml
"""
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import pytest
import yaml  # type: ignore[import-untyped]

# 加载 .env 环境变量
from bullet_trade.utils.env_loader import load_env

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 确保 jqdata 指向项目内置兼容模块，避免被系统同名包覆盖
_local_jq_path = (project_root / "jqdata.py").resolve()
try:
    import jqdata as _jq_module  # type: ignore
except ImportError:
    _jq_module = None  # type: ignore

if not _jq_module or Path(getattr(_jq_module, "__file__", "")).resolve() != _local_jq_path:
    spec = importlib.util.spec_from_file_location("jqdata", _local_jq_path)
    assert spec is not None and spec.loader is not None
    _jq_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_jq_module)  # type: ignore[arg-type]
sys.modules["jqdata"] = _jq_module  # type: ignore[arg-type]

from bullet_trade.core.engine import BacktestEngine
from bullet_trade.data.providers.base import DataProvider

NETWORK_STRATEGIES = {
    "current_data_limit_probe",
    "data_api_temporal_guards",
    "price_precision_compare",
    "strategy_small_cap_direct_provider_access",
}


class OfflineStrategyProvider(DataProvider):
    """
    策略样例测试专用离线数据源。

    职责：为默认策略回测测试提供稳定行情、交易日和指数成分，避免默认 pytest 误连真实数据源。
    核心协作对象：`BacktestEngine` 通过 `bullet_trade.data.api` 调用的全局 provider。
    关键状态：无外部连接、无磁盘缓存，所有行情由输入代码和字段即时生成。
    """

    name = "offline_strategy"

    def auth(
        self,
        user: Optional[str] = None,
        pwd: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        初始化离线 provider。

        Args:
            user: 兼容数据源认证签名，测试中不使用。
            pwd: 兼容数据源认证签名，测试中不使用。
            host: 兼容数据源认证签名，测试中不使用。
            port: 兼容数据源认证签名，测试中不使用。

        Returns:
            None。该 provider 不访问外部服务。
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
            start_date: 查询开始日期。
            end_date: 查询结束日期。
            count: 需要返回的最近交易日数量。

        Returns:
            List[datetime]: 固定工作日交易日列表。
        """
        end_ts = pd.to_datetime(end_date or "2025-12-31").normalize()
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
        返回固定行情。

        Args:
            security: 单个或多个证券代码。
            start_date: 行情开始时间。
            end_date: 行情结束时间。
            frequency: 行情频率，支持日线和分钟线形态。
            fields: 需要返回的字段。
            skip_paused: 兼容公开 API 参数，测试中不改变返回。
            fq: 兼容复权参数，测试中不改变返回。
            count: 需要返回的最近记录数量。
            panel: 多证券返回格式；False 时返回包含 code/time 的长表。
            fill_paused: 兼容公开 API 参数，测试中不改变返回。
            pre_factor_ref_date: 兼容动态复权参数，测试中不改变返回。
            prefer_engine: 兼容 provider engine 参数，测试中不改变返回。
            force_no_engine: 兼容 provider engine 参数，测试中不改变返回。

        Returns:
            pd.DataFrame: 离线行情表。
        """
        _ = skip_paused, fq, fill_paused, pre_factor_ref_date, prefer_engine, force_no_engine
        index = self._build_index(start_date, end_date, count, frequency)
        requested_fields = fields or ["open", "close", "high", "low", "volume", "money"]
        securities = security if isinstance(security, list) else [security]

        if len(securities) > 1 and not panel:
            rows = []
            for code in securities:
                for ts in index:
                    row = {"time": ts, "code": code}
                    row.update(
                        {field: self._field_value(code, field, ts) for field in requested_fields}
                    )
                    rows.append(row)
            return pd.DataFrame(rows)

        if len(securities) == 1:
            code = securities[0]
            return pd.DataFrame(
                {
                    field: [self._field_value(code, field, ts) for ts in index]
                    for field in requested_fields
                },
                index=index,
            )

        data = {
            (field, code): [self._field_value(code, field, ts) for ts in index]
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
        返回固定证券列表。

        Args:
            types: 证券类型过滤条件。
            date: 查询日期。

        Returns:
            pd.DataFrame: 包含样例策略常用标的的证券表。
        """
        _ = types, date
        return pd.DataFrame(
            {
                "display_name": [
                    "平安银行",
                    "浦发银行",
                    "万科A",
                    "中国平安",
                    "沪深300ETF",
                    "沪深300",
                ],
                "type": ["stock", "stock", "stock", "stock", "fund", "index"],
            },
            index=[
                "000001.XSHE",
                "600000.XSHG",
                "000002.XSHE",
                "601318.XSHG",
                "510300.XSHG",
                "000300.XSHG",
            ],
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
            date: 查询日期。

        Returns:
            List[str]: 固定股票池。
        """
        _ = index_symbol, date
        return [
            "000001.XSHE",
            "600000.XSHG",
            "000002.XSHE",
            "601318.XSHG",
            "510300.XSHG",
        ]

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
            List[Dict[str, Any]]: 默认样例策略不校验分红，固定返回空列表。
        """
        _ = security, start_date, end_date
        return []

    def get_security_info(
        self,
        security: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """
        返回标的类型信息。

        Args:
            security: 证券代码。
            date: 查询日期。

        Returns:
            Dict[str, Any]: 用于价格精度和交易分类的基础元数据。
        """
        _ = date
        if security.startswith(("5", "1")):
            return {"type": "fund", "category": "etf", "price_decimals": 3, "tick_decimals": 3}
        return {"type": "stock", "category": "stock", "price_decimals": 2, "tick_decimals": 2}

    def _build_index(
        self,
        start_date: Optional[Union[str, datetime]],
        end_date: Optional[Union[str, datetime]],
        count: Optional[int],
        frequency: str,
    ) -> pd.DatetimeIndex:
        """
        构造行情索引。

        Args:
            start_date: 行情开始时间。
            end_date: 行情结束时间。
            count: 需要返回的最近记录数量。
            frequency: 行情频率。

        Returns:
            pd.DatetimeIndex: 日线或分钟线索引。
        """
        end_ts = pd.to_datetime(end_date or start_date or "2025-01-01")
        freq_text = str(frequency or "daily").lower()
        is_minute = freq_text in {"minute", "1m", "1min", "min"}
        if count is not None:
            if is_minute:
                return pd.date_range(end=end_ts, periods=count, freq="min")
            return pd.bdate_range(end=end_ts.normalize(), periods=count)
        start_ts = pd.to_datetime(start_date or end_ts)
        if is_minute:
            return pd.date_range(start=start_ts, end=end_ts, freq="min")
        index = pd.bdate_range(start=start_ts.normalize(), end=end_ts.normalize())
        return index if not index.empty else pd.DatetimeIndex([end_ts.normalize()])

    def _field_value(self, code: str, field: str, ts: pd.Timestamp) -> Any:
        """
        生成字段值。

        Args:
            code: 证券代码。
            field: 行情字段名。
            ts: 当前行时间。

        Returns:
            Any: 与字段语义匹配的固定值。
        """
        code_seed = sum(ord(ch) for ch in code[-9:]) % 17
        day_seed = int(pd.Timestamp(ts).dayofyear % 11)
        base = 10.0 + code_seed * 0.1 + day_seed * 0.01
        values: Dict[str, Any] = {
            "open": round(base, 3),
            "close": round(base + 0.05, 3),
            "high": round(base + 0.2, 3),
            "low": round(base - 0.2, 3),
            "high_limit": round(base * 1.1, 3),
            "low_limit": round(base * 0.9, 3),
            "paused": False,
            "volume": 100000 + code_seed * 1000,
            "money": (100000 + code_seed * 1000) * base,
            "factor": 1.0,
        }
        return values.get(field, round(base, 3))


def load_config() -> Dict[str, Any]:
    """
    加载策略配置文件

    Returns:
        Dict[str, Any]: 配置字典
    """
    config_file = Path(__file__).parent / "strategies" / "config.yaml"

    if not config_file.exists():
        print(f"警告: 配置文件 {config_file} 不存在，使用默认配置")
        return {"default": get_default_config()}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config if config else {"default": get_default_config()}
    except Exception as e:
        print(f"警告: 加载配置文件失败: {e}，使用默认配置")
        return {"default": get_default_config()}


def discover_strategies() -> List[Tuple[str, Path]]:
    """
    发现所有策略文件

    Returns:
        List[Tuple[str, Path]]: 策略名称和文件路径的列表
    """
    strategies_dir = Path(__file__).parent / "strategies"
    strategy_files = []

    if strategies_dir.exists():
        for file_path in strategies_dir.glob("*.py"):
            # 跳过 __init__.py、测试脚本
            if file_path.name.startswith("__") or file_path.name.startswith("test_"):
                continue

            strategy_name = file_path.stem
            strategy_files.append((strategy_name, file_path))

    return sorted(strategy_files)


def load_strategy_module(strategy_path: Path):
    """
    动态加载策略模块

    Args:
        strategy_path: 策略文件路径

    Returns:
        module: 加载的策略模块
    """
    spec = importlib.util.spec_from_file_location(f"strategy_{strategy_path.stem}", strategy_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_default_config() -> Dict[str, Any]:
    """
    获取默认的策略测试配置

    Returns:
        Dict[str, Any]: 默认配置
    """
    return {
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "capital_base": 100000,
        "frequency": "daily",
        "benchmark": "000300.XSHG",
        "expected": {},
    }


def get_strategy_config(strategy_name: str, all_configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取特定策略的配置

    Args:
        strategy_name: 策略名称
        all_configs: 所有配置

    Returns:
        Dict[str, Any]: 策略配置
    """
    # 优先使用策略特定配置
    if strategy_name in all_configs:
        config = all_configs["default"].copy() if "default" in all_configs else get_default_config()
        config.update(all_configs[strategy_name])
        return config

    # 使用默认配置
    if "default" in all_configs:
        return all_configs["default"].copy()

    return get_default_config()


def validate_results(results: Dict[str, Any], expected: Dict[str, Any]) -> List[str]:
    """
    验证回测结果是否符合预期

    Args:
        results: 回测结果
        expected: 期望的结果约束

    Returns:
        List[str]: 验证失败的错误信息列表
    """
    errors = []

    for metric, constraints in expected.items():
        if metric not in results:
            continue

        actual_value = results[metric]

        # 检查最小值约束
        if "min" in constraints:
            min_value = constraints["min"]
            if actual_value < min_value:
                errors.append(f"{metric} = {actual_value:.4f} 小于期望最小值 {min_value:.4f}")

        # 检查最大值约束
        if "max" in constraints:
            max_value = constraints["max"]
            if actual_value > max_value:
                errors.append(f"{metric} = {actual_value:.4f} 大于期望最大值 {max_value:.4f}")

    return errors


# 加载配置
ALL_CONFIGS = load_config()

# 发现所有策略
STRATEGIES = [
    pytest.param(
        strategy_name,
        strategy_path,
        marks=[pytest.mark.requires_network, pytest.mark.requires_jqdata],
    )
    if strategy_name in NETWORK_STRATEGIES
    else (strategy_name, strategy_path)
    for strategy_name, strategy_path in discover_strategies()
]


@pytest.fixture(autouse=True)
def _use_offline_strategy_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    将默认策略样例测试固定到离线数据源。

    Args:
        monkeypatch: pytest 提供的临时属性替换工具。

    Returns:
        None。测试结束后自动恢复全局 provider 状态。
    """
    from bullet_trade.data import api as data_api

    provider = OfflineStrategyProvider()
    monkeypatch.setattr(data_api, "_provider", provider, raising=False)
    monkeypatch.setattr(data_api, "_provider_cache", {provider.name: provider}, raising=False)
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {provider.name: True}, raising=False)
    monkeypatch.setattr(data_api, "_auth_attempted", True, raising=False)


@pytest.mark.parametrize("strategy_name,strategy_path", STRATEGIES)
def test_strategy(strategy_name: str, strategy_path: Path):
    """
    测试单个策略

    Args:
        strategy_name: 策略名称
        strategy_path: 策略文件路径
    """
    print(f"\n{'='*60}")
    print(f"测试策略: {strategy_name}")
    print(f"文件路径: {strategy_path}")
    print(f"{'='*60}")

    # 特定策略前置检查
    if strategy_name == "data_api_temporal_guards":
        load_env()
        if not os.getenv("JQDATA_USERNAME") or not os.getenv("JQDATA_PASSWORD"):
            pytest.skip("缺少 JQDATA_USERNAME/JQDATA_PASSWORD，跳过 data_api_temporal_guards")
        try:
            __import__("jqdatasdk")
        except Exception:
            pytest.skip("未安装 jqdatasdk，跳过 data_api_temporal_guards")
    if strategy_name == "strategy_small_cap_direct_provider_access":
        load_env()
        if not os.getenv("JQDATA_USERNAME") or not os.getenv("JQDATA_PASSWORD"):
            pytest.skip("缺少 JQDATA_USERNAME/JQDATA_PASSWORD，跳过直连示例")
        try:
            __import__("jqdatasdk")
        except Exception:
            pytest.skip("未安装 jqdatasdk，跳过直连示例")
        try:
            from xtquant import xtdata  # noqa: F401
        except Exception:
            pytest.skip("缺少 miniQMT/xtquant 环境，跳过直连示例")

    # 加载策略模块前确保 jqdata 仍指向本地兼容模块（防止被其他测试污染）
    _local_jq_path = (project_root / "jqdata.py").resolve()
    jq_module = sys.modules.get("jqdata")
    if Path(getattr(jq_module, "__file__", "")).resolve() != _local_jq_path:
        spec = importlib.util.spec_from_file_location("jqdata", _local_jq_path)
        assert spec is not None and spec.loader is not None
        jq_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jq_module)  # type: ignore[arg-type]
        sys.modules["jqdata"] = jq_module  # type: ignore[arg-type]

    # 加载策略模块
    strategy_module = load_strategy_module(strategy_path)

    # 从配置文件获取策略配置（不再从策略文件读取）
    config = get_strategy_config(strategy_name, ALL_CONFIGS)

    print("\n策略配置:")
    print(f"  回测期间: {config['start_date']} ~ {config['end_date']}")
    print(f"  初始资金: {config['capital_base']:,.0f}")
    print(f"  运行频率: {config['frequency']}")
    print(f"  基准指数: {config['benchmark']}")

    # 检查必需的策略函数
    assert hasattr(strategy_module, "initialize"), f"策略 {strategy_name} 缺少 initialize 函数"

    # 创建回测引擎
    engine = BacktestEngine(
        initialize=strategy_module.initialize,
        handle_data=getattr(strategy_module, "handle_data", None),
        process_initialize=getattr(strategy_module, "process_initialize", None),
        after_trading_end=getattr(strategy_module, "after_trading_end", None),
        before_trading_start=getattr(strategy_module, "before_trading_start", None),
    )

    # 运行回测
    try:
        results = engine.run(
            start_date=config["start_date"],
            end_date=config["end_date"],
            capital_base=config["capital_base"],
            frequency=config["frequency"],
            benchmark=config["benchmark"],
        )

        # 打印关键指标
        print("\n回测结果:")
        print(f"  总收益率: {results.get('total_returns', 0):.2%}")
        print(f"  年化收益率: {results.get('annual_returns', 0):.2%}")
        print(f"  基准收益率: {results.get('benchmark_returns', 0):.2%}")
        print(f"  阿尔法: {results.get('alpha', 0):.4f}")
        print(f"  贝塔: {results.get('beta', 0):.4f}")
        print(f"  夏普比率: {results.get('sharpe', 0):.4f}")
        print(f"  最大回撤: {results.get('max_drawdown', 0):.2%}")
        print(f"  胜率: {results.get('win_rate', 0):.2%}")

        # 验证结果
        if config.get("expected"):
            print("\n验证结果约束...")
            errors = validate_results(results, config["expected"])

            if errors:
                error_msg = "\n".join(errors)
                pytest.fail(f"策略 {strategy_name} 未满足预期约束:\n{error_msg}")
            else:
                print("  ✓ 所有约束条件均已满足")

        print(f"\n{'='*60}")
        print(f"策略 {strategy_name} 测试通过 ✓")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n策略运行失败: {str(e)}")
        raise


def test_no_strategies_warning():
    """
    如果没有发现任何策略，给出警告
    """
    if not STRATEGIES:
        pytest.skip("未发现任何策略文件，请在 tests/strategies/ 目录下添加策略文件")


if __name__ == "__main__":
    # 直接运行此文件时，使用 pytest
    pytest.main([__file__, "-v", "-s"])
