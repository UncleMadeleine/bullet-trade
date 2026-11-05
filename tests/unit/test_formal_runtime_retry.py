from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
COMMON_ROOT = WORKSPACE_ROOT / "strategies" / "bt_strategies" / "sim" / "common"
PRIVATE_LIVE_ROOT = COMMON_ROOT / "private_live"
FORMAL_RUNTIME_PATH = PRIVATE_LIVE_ROOT / "formal_runtime.py"


def _ensure_package(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module


_ensure_package("bt_strategies", WORKSPACE_ROOT / "strategies" / "bt_strategies")
_ensure_package("bt_strategies.sim", WORKSPACE_ROOT / "strategies" / "bt_strategies" / "sim")
_ensure_package("bt_strategies.sim.common", COMMON_ROOT)
_ensure_package("bt_strategies.sim.common.private_live", PRIVATE_LIVE_ROOT)

spec = importlib.util.spec_from_file_location(
    "bt_strategies.sim.common.private_live.formal_runtime_test_module",
    FORMAL_RUNTIME_PATH,
)
assert spec is not None and spec.loader is not None
formal_runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = formal_runtime
spec.loader.exec_module(formal_runtime)


@pytest.mark.unit
def test_retry_failed_buys_keeps_submitted_when_order_waits_for_settlement(monkeypatch):
    plan = {
        "submitted_buy_codes": ["127085"],
        "pending_buy_codes": ["127085"],
    }
    state = {"logs": []}

    monkeypatch.setattr(
        formal_runtime,
        "_latest_order_tracking_map",
        lambda codes, side=None: {
            "127085": {
                "status": "canceled",
                "filled": 0,
                "settlement_state": "pending",
            }
        },
    )

    formal_runtime._retry_failed_buys(plan, state)

    assert plan["submitted_buy_codes"] == ["127085"]
    assert any("settlement_state=pending" in item for item in state["logs"])


@pytest.mark.unit
def test_retry_failed_buys_reopens_retry_for_real_failed_order(monkeypatch):
    plan = {
        "submitted_buy_codes": ["127085"],
        "pending_buy_codes": ["127085"],
    }
    state = {"logs": []}

    monkeypatch.setattr(
        formal_runtime,
        "_latest_order_tracking_map",
        lambda codes, side=None: {
            "127085": {
                "status": "canceled",
                "filled": 0,
                "settlement_state": "settled",
            }
        },
    )

    formal_runtime._retry_failed_buys(plan, state)

    assert plan["submitted_buy_codes"] == []
    assert any("允许下轮重试 127085" in item for item in state["logs"])
