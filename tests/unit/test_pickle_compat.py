"""
作者: BruceLee
文件职责: 验证 JQData pickle 兼容层在新老 numpy/pandas 环境下的模块别名行为。
主要输入: 临时修改后的 sys.modules 状态。
主要输出: pytest 断言，确保兼容层只补缺失模块且不覆盖真实模块。
上下游关系: 覆盖 bullet_trade.data.pickle_compat，被 JQDataProvider 导入前调用。
关键环境或配置约定: 测试会恢复 sys.modules，避免污染其他用例。
"""

from __future__ import annotations

import sys
import types
from typing import Dict, Optional

import pytest

from bullet_trade.data.pickle_compat import install_pickle_compat_shims

PICKLE_COMPAT_MODULES = (
    "numpy._core",
    "numpy._core.numeric",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "numpy._core._multiarray_umath",
    "pandas.core.indexes.numeric",
    "pandas.core.indexes.frozen",
)


def _snapshot_modules() -> Dict[str, Optional[types.ModuleType]]:
    """
    保存测试涉及的模块状态。

    Returns:
        Dict[str, Optional[types.ModuleType]]: 模块名到原始模块对象的映射，不存在时为 None。
    """
    return {name: sys.modules.get(name) for name in PICKLE_COMPAT_MODULES}


def _restore_modules(original: Dict[str, Optional[types.ModuleType]]) -> None:
    """
    恢复测试前的模块状态。

    Args:
        original: _snapshot_modules 返回的原始模块映射。
    """
    for name in PICKLE_COMPAT_MODULES:
        sys.modules.pop(name, None)
    for name, module in original.items():
        if module is not None:
            sys.modules[name] = module


@pytest.mark.unit
def test_install_pickle_compat_shims_registers_missing_numpy_core_aliases():
    """
    验证老 numpy 环境缺少 numpy._core 时会注册兼容别名。
    """
    original = _snapshot_modules()
    for name in PICKLE_COMPAT_MODULES:
        sys.modules.pop(name, None)

    try:
        install_pickle_compat_shims()

        assert "numpy._core" in sys.modules
        assert "numpy._core.numeric" in sys.modules
        assert "numpy._core.multiarray" in sys.modules
        assert "numpy._core.umath" in sys.modules
        assert "numpy._core._multiarray_umath" in sys.modules
        assert "pandas.core.indexes.numeric" in sys.modules
        assert "pandas.core.indexes.frozen" in sys.modules
    finally:
        _restore_modules(original)


@pytest.mark.unit
def test_install_pickle_compat_shims_preserves_existing_numpy_core_module():
    """
    验证新 numpy 环境已有 numpy._core 时不会被兼容层覆盖。
    """
    original = _snapshot_modules()
    existing = types.ModuleType("numpy._core")
    for name in PICKLE_COMPAT_MODULES:
        sys.modules.pop(name, None)
    sys.modules["numpy._core"] = existing

    try:
        install_pickle_compat_shims()

        assert sys.modules["numpy._core"] is existing
        assert hasattr(existing, "numeric")
        assert "pandas.core.indexes.numeric" in sys.modules
        assert "pandas.core.indexes.frozen" in sys.modules
    finally:
        _restore_modules(original)
