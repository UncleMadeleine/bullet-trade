"""
作者: BruceLee
文件职责: 安装 JQData pickle 反序列化所需的 numpy/pandas 兼容别名。
主要输入: 当前 Python 进程已安装的 numpy 与 pandas 模块。
主要输出: 注册到 sys.modules 的兼容模块别名与最小替身类。
上下游关系: 由 JQDataProvider 在导入 jqdatasdk 前安装，用于兼容新老 numpy/pandas 生成的 pickle。
关键环境或配置约定: 只补缺失模块，不覆盖新环境已经存在的真实模块。
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any, Optional, Tuple, Type, cast

import numpy as np
import pandas as pd


class _CompatModule(types.ModuleType):
    """
    pandas 旧 pickle 路径使用的最小模块替身。

    该类只承担模块容器职责，不实现额外行为。
    """


class _CompatNumericIndex:
    """
    pandas 旧 NumericIndex 类的反序列化替身。

    pickle 反序列化旧 pandas 索引时可能查找 Int64Index、UInt64Index 或 Float64Index。
    新 pandas 已统一到 Index，这里将构造请求转给 pd.Index。
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> pd.Index:
        """
        创建兼容的 pandas Index。

        Args:
            *args: pickle 传入的索引构造位置参数。
            **kwargs: pickle 传入的索引构造关键字参数。

        Returns:
            pd.Index: pandas 当前版本可识别的索引对象。
        """
        return pd.Index(*args, **kwargs)


class _CompatFrozenNDArray(np.ndarray):
    """
    pandas 旧 FrozenNDArray 类的反序列化替身。

    pickle 只需要该类参与 ndarray 重建；最终返回普通 ndarray 语义即可。
    """

    def __new__(cls, *args: Any, **_kwargs: Any) -> "_CompatFrozenNDArray":
        """
        创建兼容的 ndarray 对象。

        Args:
            *args: pickle 传入的数组构造位置参数。
            **_kwargs: pickle 传入但当前替身不使用的关键字参数。

        Returns:
            np.ndarray: 当前 numpy 可识别的数组对象。
        """
        if args and isinstance(args[0], (list, tuple, np.ndarray)):
            return cast("_CompatFrozenNDArray", np.array(args[0]).view(cls))
        return cast("_CompatFrozenNDArray", np.array([]).view(cls))

    @staticmethod
    def _reconstruct(subtype: Type[Any], shape: Tuple[int, ...], dtype: Any) -> np.ndarray:
        """
        按 numpy pickle 协议重建数组。

        Args:
            subtype: pickle 请求重建的数组子类。
            shape: 数组形状。
            dtype: 数组数据类型。

        Returns:
            np.ndarray: 重建后的数组对象。
        """
        if subtype is _CompatFrozenNDArray:
            return np.ndarray._reconstruct(np.ndarray, shape, dtype)  # type: ignore[attr-defined]
        return np.ndarray._reconstruct(subtype, shape, dtype)  # type: ignore[attr-defined]


def _import_optional_module(module_name: str) -> Optional[types.ModuleType]:
    """
    安全导入可选模块。

    Args:
        module_name: 需要导入的模块名。

    Returns:
        Optional[types.ModuleType]: 导入成功返回模块，失败返回 None。
    """
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _ensure_numpy_core_alias() -> None:
    """
    确保 numpy._core 及常用子模块在 sys.modules 中存在。

    新 numpy 环境如果已经提供 numpy._core，则保留真实模块；老 numpy 环境没有该路径时，
    将其映射到 numpy.core，使新环境生成的 pickle 能在老环境反序列化。
    """
    real_core = _import_optional_module("numpy._core")
    if real_core is not None:
        proxy = real_core
    elif "numpy._core" in sys.modules:
        proxy = sys.modules["numpy._core"]
    else:
        old_core = _import_optional_module("numpy.core")
        proxy = types.ModuleType("numpy._core")
        if old_core is not None:
            proxy.__dict__.update(getattr(old_core, "__dict__", {}))
        proxy.__package__ = "numpy"
        proxy.__path__ = []  # type: ignore[attr-defined]
        sys.modules["numpy._core"] = proxy

    for name in ("numeric", "multiarray", "umath", "_multiarray_umath"):
        if f"numpy._core.{name}" in sys.modules:
            setattr(proxy, name, sys.modules[f"numpy._core.{name}"])
            continue

        target = _import_optional_module(f"numpy._core.{name}")
        if target is None:
            target = _import_optional_module(f"numpy.core.{name}")
        if target is None:
            target = getattr(getattr(np, "core", object()), name, None)
        if target is not None:
            setattr(proxy, name, target)
            sys.modules.setdefault(f"numpy._core.{name}", target)


def _ensure_pandas_pickle_aliases() -> None:
    """
    确保 pandas 旧索引 pickle 路径存在。

    pandas 2.x 移除了部分旧模块路径；老版本或远端环境生成的 pickle 仍可能引用这些路径。
    这里仅在模块缺失时安装最小替身，避免覆盖真实 pandas 模块。
    """
    if "pandas.core.indexes.numeric" not in sys.modules:
        numeric_module = _CompatModule("pandas.core.indexes.numeric")
        numeric_alias = cast(Any, numeric_module)
        numeric_alias.Int64Index = _CompatNumericIndex
        numeric_alias.UInt64Index = _CompatNumericIndex
        numeric_alias.Float64Index = _CompatNumericIndex
        numeric_alias.NumericIndex = _CompatNumericIndex
        sys.modules["pandas.core.indexes.numeric"] = numeric_module

    if "pandas.core.indexes.frozen" not in sys.modules:
        frozen_module = _CompatModule("pandas.core.indexes.frozen")
        cast(Any, frozen_module).FrozenNDArray = _CompatFrozenNDArray
        sys.modules["pandas.core.indexes.frozen"] = frozen_module


def install_pickle_compat_shims() -> None:
    """
    安装 JQData pickle 兼容别名。

    Returns:
        None: 该函数只修改当前进程的 sys.modules。

    Side Effects:
        在缺失时注册 numpy._core、numpy._core 子模块以及 pandas 旧索引模块替身。
    """
    _ensure_numpy_core_alias()
    _ensure_pandas_pickle_aliases()


__all__ = ["install_pickle_compat_shims"]
