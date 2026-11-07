"""
AKShare 数据源适配器

文件职责：通过 akshare 公开接口提供聚宽兼容的免费行情数据。
主要输入：聚宽风格证券代码、日期范围、频率、字段、复权参数。
主要输出：聚宽兼容的 DataFrame、交易日列表、证券列表、指数成分、分红事件，
以及估值与财务快照（PB/PE、市场PB分位、ROE/营收增速/行业）。
上下游关系：由 bullet_trade.data.api 的 provider 工厂按显式名称 akshare 创建。
关键约定：akshare 延迟导入；该数据源属于公开网页聚合，仅作为 Beta/补充源，
历史证券列表和指数成分只能返回最新结果，不保证回测时点准确性。
"""

from __future__ import annotations

import importlib
import math
from datetime import date as Date
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from .base import DataProvider
from ..cache import CacheManager

_DEFAULT_PRICE_FIELDS = ["open", "close", "high", "low", "volume", "money"]
_PRICE_FIELDS = {"open", "close", "high", "low", "pre_close", "high_limit", "low_limit"}
_COLUMN_MAP = {
    "日期": "time",
    "时间": "time",
    "date": "time",
    "datetime": "time",
    "开盘": "open",
    "开盘价": "open",
    "收盘": "close",
    "收盘价": "close",
    "最高": "high",
    "最高价": "high",
    "最低": "low",
    "最低价": "low",
    "成交量": "volume",
    "成交额": "money",
    "昨收": "pre_close",
    "代码": "code",
    "名称": "name",
}
_DAILY_FREQUENCIES = {
    "daily": "daily",
    "1d": "daily",
    "d": "daily",
    "day": "daily",
    "weekly": "weekly",
    "1w": "weekly",
    "w": "weekly",
    "monthly": "monthly",
    "1M": "monthly",
}
_MINUTE_FREQUENCIES = {
    "minute": "1",
    "1m": "1",
    "m1": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}
_BARS_PER_DAY = {"1": 240, "5": 48, "15": 16, "30": 8, "60": 4}
_INDEX_CODE_PREFIXES = ("000", "399", "899")


class AkshareProvider(DataProvider):
    """AKShare 免费行情数据源，负责把公开网页数据转换为聚宽兼容格式。"""

    name: str = "akshare"
    requires_live_data: bool = False

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化 provider；不在构造阶段导入 akshare 或发起网络请求。"""
        self.config = config or {}
        cache_dir_set = "cache_dir" in self.config
        cache_dir = self.config.get("cache_dir")
        self._cache = CacheManager(
            provider_name=self.name,
            cache_dir=cache_dir,
            fallback_to_env=not cache_dir_set,
        )
        self._ak: Optional[Any] = self.config.get("akshare")
        self._authenticated = False

    # ------------------------ 公共工具 ------------------------
    def _ensure_akshare(self) -> Any:
        """延迟导入 akshare；缺失时抛出带安装指引的 ImportError。"""
        if self._ak is not None:
            return self._ak
        try:
            self._ak = importlib.import_module("akshare")
        except ImportError as exc:  # pragma: no cover - 只在真实缺依赖时触发
            raise ImportError(
                "未安装 akshare，请执行 `pip install bullet-trade[akshare]` 或 `pip install akshare`"
            ) from exc
        return self._ak

    def auth(
        self,
        user: Optional[str] = None,
        pwd: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """AKShare 无需认证；这里只确认依赖可用。"""
        _ = user, pwd, host, port
        self._ensure_akshare()
        self._authenticated = True

    @staticmethod
    def _as_list(security: Union[str, Sequence[str]]) -> List[str]:
        """把单证券或证券序列统一为字符串列表。"""
        if isinstance(security, str):
            return [security]
        if security is None:
            return []
        return [str(item) for item in security]

    @staticmethod
    def _to_ak_symbol(security: str) -> str:
        """把聚宽或带市场前缀的代码转换为 akshare 常用的 6 位代码。"""
        text = str(security).strip()
        if "." in text:
            prefix, suffix = text.split(".", 1)
            if prefix.upper() in {"SHSE", "SZSE", "BJSE", "BSE"}:
                return suffix
            return prefix
        if text.lower().startswith(("sh", "sz", "bj")) and len(text) > 2:
            return text[2:]
        return text

    @staticmethod
    def _infer_suffix(code: str, kind: str = "stock") -> str:
        """按代码段和资产类型推断聚宽市场后缀。"""
        code = str(code).zfill(6)
        if kind == "index":
            if code.startswith("399"):
                return "XSHE"
            if code.startswith("899"):
                return "BJ"
            return "XSHG"
        if code.startswith(("4", "8")):
            return "BJ"
        if code.startswith(("5", "6", "9")):
            return "XSHG"
        return "XSHE"

    @classmethod
    def _to_jq_code(
        cls,
        code: Any,
        exchange: Optional[str] = None,
        kind: str = "stock",
    ) -> str:
        """把 akshare 返回的代码和交易所信息转换为聚宽格式。"""
        raw = str(code).strip()
        if not raw:
            return ""
        if "." in raw:
            prefix, suffix = raw.rsplit(".", 1)
            if suffix.upper() in {"SH", "XSHG"}:
                return f"{prefix.zfill(6)}.XSHG"
            if suffix.upper() in {"SZ", "XSHE"}:
                return f"{prefix.zfill(6)}.XSHE"
            if suffix.upper() in {"BJ", "BSE", "XBJG"}:
                return f"{prefix.zfill(6)}.BJ"
            return raw
        digits = "".join(ch for ch in raw if ch.isdigit()).zfill(6)
        ex = str(exchange or "").upper()
        if "SH" in ex or "上海" in str(exchange or ""):
            return f"{digits}.XSHG"
        if "SZ" in ex or "深圳" in str(exchange or ""):
            return f"{digits}.XSHE"
        if "BJ" in ex or "北京" in str(exchange or ""):
            return f"{digits}.BJ"
        return f"{digits}.{cls._infer_suffix(digits, kind=kind)}"

    @classmethod
    def _infer_asset_kind(cls, security: str) -> str:
        """按代码段推断 stock/etf/lof/index。"""
        code = cls._to_ak_symbol(security).zfill(6)
        suffix = str(security).rsplit(".", 1)[-1].upper() if "." in str(security) else ""
        if suffix in {"XSHG", "SH"} and code.startswith("000"):
            return "index"
        if suffix in {"XSHE", "SZ"} and code.startswith("399"):
            return "index"
        if code.startswith("899"):
            return "index"
        if code.startswith(("15", "50", "51", "52", "56", "58")):
            return "etf"
        if code.startswith(("16", "18")):
            return "lof"
        return "stock"

    @classmethod
    def _infer_jq_security_type(cls, security: str) -> str:
        """把内部资产类别映射为聚宽证券类型。"""
        kind = cls._infer_asset_kind(security)
        if kind == "index":
            return "index"
        if kind in {"etf", "lof"}:
            return "fund"
        return "stock"

    # ------------------------ 频率与日期 ------------------------
    @staticmethod
    def _normalize_frequency(frequency: str) -> str:
        """把聚宽频率标准化为内部字符串。"""
        freq = str(frequency or "daily").strip()
        if freq == "1M":
            return "monthly"
        lower = freq.lower()
        if lower in _DAILY_FREQUENCIES:
            return lower if lower != "d" else "daily"
        return lower

    @classmethod
    def _is_intraday(cls, frequency: str) -> bool:
        """判断频率是否属于分钟级。"""
        return cls._normalize_frequency(frequency) in _MINUTE_FREQUENCIES

    @classmethod
    def _resolve_daily_period(cls, frequency: str) -> str:
        """把日线频率映射为 akshare 的 daily/weekly/monthly。"""
        freq = cls._normalize_frequency(frequency)
        return _DAILY_FREQUENCIES.get(freq, "daily")

    @classmethod
    def _resolve_minute_period(cls, frequency: str) -> str:
        """把分钟频率映射为 akshare 的 1/5/15/30/60。"""
        freq = cls._normalize_frequency(frequency)
        return _MINUTE_FREQUENCIES.get(freq, "1")

    @staticmethod
    def _resolve_adjust(fq: Optional[str]) -> str:
        """把聚宽复权参数映射为 akshare 的 qfq/hfq 空串。"""
        value = str(fq or "").lower().strip()
        if value in {"pre", "qfq"}:
            return "qfq"
        if value in {"post", "hfq"}:
            return "hfq"
        return ""

    @classmethod
    def _bars_per_day(cls, frequency: str) -> int:
        """返回分钟频率对应的单日 bar 数。"""
        return _BARS_PER_DAY.get(cls._resolve_minute_period(frequency), 1)

    @staticmethod
    def _as_timestamp(value: Optional[Union[str, datetime, Date]]) -> Optional[pd.Timestamp]:
        """把日期参数转换为 pandas Timestamp。"""
        if value is None or value == "":
            return None
        try:
            parsed = pd.to_datetime(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed)

    @staticmethod
    def _format_daily(value: pd.Timestamp) -> str:
        """把时间转换为 akshare 日线接口使用的 YYYYMMDD。"""
        return value.strftime("%Y%m%d")

    @staticmethod
    def _format_minute(value: pd.Timestamp) -> str:
        """把时间转换为 akshare 分钟接口使用的 YYYY-MM-DD HH:MM:SS。"""
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _resolve_window(
        self,
        *,
        start_date: Optional[Union[str, datetime]],
        end_date: Optional[Union[str, datetime]],
        frequency: str,
        count: Optional[int],
    ) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """推算实际请求窗口，避免 count 请求拉取全量历史。"""
        end_ts = self._as_timestamp(end_date) or pd.Timestamp.now()
        start_ts = self._as_timestamp(start_date)
        intraday = self._is_intraday(frequency)
        if intraday and end_ts.time() == datetime.min.time():
            end_ts = end_ts.replace(hour=15, minute=0, second=0)
        if start_ts is not None:
            return start_ts, end_ts
        if count is not None:
            if intraday:
                bars = max(self._bars_per_day(frequency), 1)
                days = max(int(math.ceil(float(count) / float(bars))) + 5, 5)
            else:
                period = self._resolve_daily_period(frequency)
                if period == "weekly":
                    days = max(int(count) * 9 + 20, 30)
                elif period == "monthly":
                    days = max(int(count) * 40 + 60, 60)
                else:
                    days = max(int(count) * 2 + 10, 30)
            return end_ts - pd.Timedelta(days=days), end_ts
        if intraday:
            return end_ts - pd.Timedelta(days=5), end_ts
        return pd.Timestamp("2015-01-01"), end_ts

    # ------------------------ 价格数据 ------------------------
    @staticmethod
    def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
        """把 akshare 中文列名转换为内部字段名。"""
        result = df.copy()
        rename = {col: _COLUMN_MAP[col] for col in result.columns if col in _COLUMN_MAP}
        if rename:
            result.rename(columns=rename, inplace=True)
        return result

    @classmethod
    def _normalize_price_frame(
        cls,
        raw: Any,
        *,
        fields: List[str],
        frequency: str,
    ) -> pd.DataFrame:
        """把 akshare K 线返回值转换为 index=time 的聚宽字段表。"""
        df = pd.DataFrame(raw)
        if df.empty:
            return pd.DataFrame()
        df = cls._rename_columns(df)
        if "time" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                index_name = df.index.name or "index"
                df = df.reset_index().rename(columns={index_name: "time"})
            else:
                return pd.DataFrame()
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df.dropna(subset=["time"], inplace=True)
        if df.empty:
            return pd.DataFrame()
        df.set_index("time", inplace=True)
        df.sort_index(inplace=True)
        for field in _DEFAULT_PRICE_FIELDS:
            if field not in df.columns:
                df[field] = 0.0
            else:
                df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0.0)
        # 东方财富成交量单位为手，统一换算为股。
        df["volume"] = df["volume"] * 100.0
        if "pre_close" not in df.columns and "close" in df.columns:
            df["pre_close"] = df["close"].shift(1)
        if "avg" in fields:
            volume = df["volume"].where(df["volume"] != 0)
            df["avg"] = df["money"] / volume
        for field in fields:
            if field not in df.columns:
                if field == "paused":
                    df[field] = False
                elif field == "factor":
                    df[field] = 1.0
                else:
                    df[field] = 0.0
        return df[[field for field in fields if field in df.columns]]

    def _fetch_price_uncached(
        self,
        security: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        frequency: str,
        fields: List[str],
        fq: Optional[str],
        count: Optional[int],
    ) -> pd.DataFrame:
        """调用 akshare 获取单证券 K 线并标准化。"""
        ak = self._ensure_akshare()
        kind = self._infer_asset_kind(security)
        symbol = self._to_ak_symbol(security)
        adjust = self._resolve_adjust(fq)
        intraday = self._is_intraday(frequency)
        try:
            if intraday:
                period = self._resolve_minute_period(frequency)
                start_text = self._format_minute(start_date)
                end_text = self._format_minute(end_date)
                if kind == "index":
                    raw = ak.index_zh_a_hist_min_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                    )
                elif kind == "etf":
                    raw = ak.fund_etf_hist_min_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
                elif kind == "lof":
                    raw = ak.fund_lof_hist_min_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
                else:
                    raw = ak.stock_zh_a_hist_min_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
            else:
                period = self._resolve_daily_period(frequency)
                start_text = self._format_daily(start_date)
                end_text = self._format_daily(end_date)
                if kind == "index":
                    raw = ak.index_zh_a_hist(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                    )
                elif kind == "etf":
                    raw = ak.fund_etf_hist_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
                elif kind == "lof":
                    raw = ak.fund_lof_hist_em(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
                else:
                    raw = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period=period,
                        start_date=start_text,
                        end_date=end_text,
                        adjust=adjust,
                    )
        except Exception as exc:
            raise RuntimeError(f"AKShare 获取 {security} 行情失败: {exc}") from exc
        frame = self._normalize_price_frame(raw, fields=fields, frequency=frequency)
        if frame.empty:
            return frame
        if intraday:
            frame = frame[frame.index <= end_date]
        else:
            frame = frame[frame.index.normalize() <= end_date.normalize()]
        if start_date is not None:
            frame = frame[frame.index >= start_date]
        if count is not None and not frame.empty:
            frame = frame.tail(int(count))
        return frame

    def _fetch_price_single(
        self,
        security: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        frequency: str,
        fields: List[str],
        fq: Optional[str],
        count: Optional[int],
    ) -> pd.DataFrame:
        """带磁盘缓存的单证券行情读取。"""
        kwargs = {
            "security": security,
            "start_date": start_date,
            "end_date": end_date,
            "frequency": frequency,
            "fields": fields,
            "fq": fq,
            "count": count,
        }

        def _fetch(params: Dict[str, Any]) -> pd.DataFrame:
            return self._fetch_price_uncached(
                security,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                fields=fields,
                fq=fq,
                count=count,
            )

        return self._cache.cached_call("get_price", kwargs, _fetch, result_type="df")

    @staticmethod
    def _assemble_price_result(
        frames: Dict[str, pd.DataFrame],
        *,
        fields: List[str],
        securities: List[str],
        panel: bool,
    ) -> pd.DataFrame:
        """按聚宽兼容 shape 组装单证券、多证券、panel 和长表。"""
        if not frames:
            return pd.DataFrame()
        if len(securities) == 1 and panel:
            return frames.get(securities[0], pd.DataFrame())
        if panel:
            parts = []
            for field in fields:
                field_frames = []
                for security in securities:
                    df = frames.get(security)
                    if df is None or df.empty:
                        continue
                    series = (
                        df[field]
                        if field in df.columns
                        else pd.Series(index=df.index, dtype="float64")
                    )
                    field_frames.append(series.rename(security))
                if field_frames:
                    parts.append(pd.concat(field_frames, axis=1))
                else:
                    parts.append(pd.DataFrame(columns=securities))
            wide = pd.concat(parts, axis=1, keys=fields)
            wide.columns.names = ["field", "code"]
            wide.sort_index(inplace=True)
            return wide
        rows = []
        for security in securities:
            df = frames.get(security)
            if df is None or df.empty:
                continue
            part = df.copy().reset_index().rename(columns={"index": "time"})
            if "time" not in part.columns:
                part.rename(columns={part.columns[0]: "time"}, inplace=True)
            part["code"] = security
            for field in fields:
                if field not in part.columns:
                    part[field] = False if field == "paused" else 0.0
            rows.append(part[["time", "code"] + fields])
        if not rows:
            return pd.DataFrame()
        return (
            pd.concat(rows, ignore_index=True).sort_values(["time", "code"]).reset_index(drop=True)
        )

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
        """获取 AKShare K 线；分钟历史深度由数据源决定。"""
        _ = skip_paused, fill_paused, pre_factor_ref_date, prefer_engine, force_no_engine
        securities = self._as_list(security)
        if not securities:
            return pd.DataFrame()
        requested_fields = list(fields or _DEFAULT_PRICE_FIELDS)
        frequency_norm = self._normalize_frequency(frequency)
        start_ts, end_ts = self._resolve_window(
            start_date=start_date,
            end_date=end_date,
            frequency=frequency_norm,
            count=count,
        )
        frames: Dict[str, pd.DataFrame] = {}
        for sec in securities:
            frames[sec] = self._fetch_price_single(
                sec,
                start_date=start_ts,
                end_date=end_ts,
                frequency=frequency_norm,
                fields=requested_fields,
                fq=fq,
                count=count,
            )
        return self._assemble_price_result(
            frames,
            fields=requested_fields,
            securities=securities,
            panel=panel,
        )

    def get_bars(
        self,
        security: Union[str, List[str]],
        count: int,
        unit: str = "1d",
        fields: Optional[List[str]] = None,
        include_now: bool = False,
        end_dt: Optional[Union[str, datetime]] = None,
        fq_ref_date: Union[int, datetime] = 1,
        df: bool = False,
    ) -> Any:
        """用 get_price 提供聚宽 get_bars 兼容入口。"""
        _ = include_now, fq_ref_date
        request_fields = [field for field in (fields or _DEFAULT_PRICE_FIELDS) if field != "date"]
        frequency = "daily" if str(unit).lower() in {"1d", "d", "day", "daily"} else unit
        result = self.get_price(
            security=security,
            end_date=end_dt,
            frequency=frequency,
            fields=request_fields,
            count=count,
            fq="pre",
            panel=df,
        )
        if df or not isinstance(result, pd.DataFrame):
            return result
        return result.to_dict()

    # ------------------------ 交易日 ------------------------
    def _fetch_trade_days(
        self,
        *,
        start_date: Optional[Union[str, datetime]],
        end_date: Optional[Union[str, datetime]],
        count: Optional[int],
    ) -> List[str]:
        """拉取并裁剪交易日，返回 ISO 字符串以适配缓存。"""
        ak = self._ensure_akshare()
        raw = ak.tool_trade_date_hist_sina()
        df = pd.DataFrame(raw)
        if df.empty:
            return []
        column = "trade_date" if "trade_date" in df.columns else df.columns[0]
        dates = pd.to_datetime(df[column], errors="coerce").dropna().dt.date
        start_ts = self._as_timestamp(start_date)
        end_ts = self._as_timestamp(end_date)
        if start_ts is not None:
            dates = dates[dates >= start_ts.date()]
        if end_ts is not None:
            dates = dates[dates <= end_ts.date()]
        if count is not None:
            tail_count = int(count)
            dates = dates[-tail_count:]
        return [item.isoformat() for item in dates]

    def get_trade_days(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        count: Optional[int] = None,
    ) -> List[datetime]:
        """获取交易日列表。"""
        kwargs = {"start_date": start_date, "end_date": end_date, "count": count}
        values = self._cache.cached_call(
            "get_trade_days",
            kwargs,
            lambda _: self._fetch_trade_days(start_date=start_date, end_date=end_date, count=count),
            result_type="list_str",
        )
        return [pd.Timestamp(item).to_pydatetime() for item in values]

    def get_trade_day(self, security: Union[str, List[str]], query_dt: Union[str, datetime]) -> Any:
        """返回指定时间之前最近的一个交易日。"""
        try:
            trade_days = self.get_trade_days(end_date=query_dt, count=1)
        except Exception:
            trade_days = []
        last_day = None
        if trade_days:
            try:
                last_day = pd.to_datetime(trade_days[-1]).date()
            except Exception:
                last_day = trade_days[-1]
        if isinstance(security, (list, tuple, set)):
            securities = list(security)
        else:
            securities = [security]
        return {str(sec): last_day for sec in securities}

    # ------------------------ 证券列表 ------------------------
    @staticmethod
    def _pick_column(df: pd.DataFrame, *names: str) -> Optional[str]:
        """从 DataFrame 中挑选第一个存在的列名。"""
        for name in names:
            if name in df.columns:
                return name
        return None

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        """把字段安全转换为浮点数。"""
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _resolve_security_types(self, types: Union[str, List[str]]) -> List[str]:
        """展开 get_all_securities 的类型参数。"""
        requested = {types} if isinstance(types, str) else {str(item) for item in types or []}
        requested = {item.lower() for item in requested}
        result: List[str] = []
        if "all" in requested:
            return ["stock", "etf", "lof", "index"]
        if "stock" in requested:
            result.append("stock")
        if "fund" in requested or "etf" in requested:
            result.append("etf")
        if "fund" in requested or "lof" in requested:
            result.append("lof")
        if "index" in requested:
            result.append("index")
        return result

    def _fetch_all_securities(
        self,
        *,
        types: Union[str, List[str]],
        date: Optional[Union[str, datetime]],
    ) -> pd.DataFrame:
        """拉取当前证券列表；历史时点无法还原。"""
        ak = self._ensure_akshare()
        rows: List[Dict[str, Any]] = []
        for kind in self._resolve_security_types(types):
            try:
                if kind == "stock":
                    raw = ak.stock_info_a_code_name()
                    df = pd.DataFrame(raw)
                    code_col = self._pick_column(df, "code", "代码")
                    name_col = self._pick_column(df, "name", "名称")
                    for _, row in df.iterrows():
                        code = row.get(code_col)
                        if code is None:
                            continue
                        rows.append(
                            {
                                "code": self._to_jq_code(code),
                                "display_name": row.get(name_col) or str(code),
                                "name": row.get(name_col) or str(code),
                                "start_date": Date(1990, 12, 19),
                                "end_date": Date(2200, 1, 1),
                                "type": "stock",
                            }
                        )
                elif kind in {"etf", "lof"}:
                    getter = ak.fund_etf_spot_em if kind == "etf" else ak.fund_lof_spot_em
                    df = pd.DataFrame(getter())
                    code_col = self._pick_column(df, "代码", "code")
                    name_col = self._pick_column(df, "名称", "name")
                    for _, row in df.iterrows():
                        code = row.get(code_col)
                        if code is None:
                            continue
                        rows.append(
                            {
                                "code": self._to_jq_code(code),
                                "display_name": row.get(name_col) or str(code),
                                "name": row.get(name_col) or str(code),
                                "start_date": Date(1990, 12, 19),
                                "end_date": Date(2200, 1, 1),
                                "type": "fund",
                            }
                        )
                elif kind == "index":
                    df = pd.DataFrame(ak.index_stock_info())
                    code_col = self._pick_column(df, "index_code", "代码")
                    name_col = self._pick_column(df, "display_name", "名称")
                    date_col = self._pick_column(df, "publish_date", "发布日期")
                    for _, row in df.iterrows():
                        code = row.get(code_col)
                        if code is None:
                            continue
                        publish = row.get(date_col)
                        start = (
                            pd.to_datetime(publish, errors="coerce").date()
                            if publish is not None and not pd.isna(publish)
                            else Date(1990, 12, 19)
                        )
                        rows.append(
                            {
                                "code": self._to_jq_code(code, kind="index"),
                                "display_name": row.get(name_col) or str(code),
                                "name": row.get(name_col) or str(code),
                                "start_date": start,
                                "end_date": Date(2200, 1, 1),
                                "type": "index",
                            }
                        )
            except Exception:
                continue
        if not rows:
            return pd.DataFrame(columns=["display_name", "name", "start_date", "end_date", "type"])
        result = pd.DataFrame(rows).drop_duplicates(subset=["code"]).set_index("code")
        query_date = self._as_timestamp(date)
        if query_date is not None:
            day = query_date.date()
            result = result[(result["start_date"] <= day) & (result["end_date"] >= day)]
        return result

    def get_all_securities(
        self,
        types: Union[str, List[str]] = "stock",
        date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        """获取当前证券列表；仅支持最新快照。"""
        kwargs = {"types": types, "date": date}
        return self._cache.cached_call(
            "get_all_securities",
            kwargs,
            lambda _: self._fetch_all_securities(types=types, date=date),
            result_type="df",
        )

    # ------------------------ 指数成分 ------------------------
    def _extract_index_codes(self, df: pd.DataFrame) -> List[str]:
        """从不同 akshare 指数成分表提取聚宽代码。"""
        if df.empty:
            return []
        code_col = self._pick_column(df, "成分券代码", "品种代码", "代码", "证券代码")
        if code_col is None:
            return []
        exchange_col = self._pick_column(df, "交易所", "交易所英文名称")
        result: List[str] = []
        for _, row in df.iterrows():
            code = row.get(code_col)
            if code is None or pd.isna(code):
                continue
            exchange = row.get(exchange_col) if exchange_col else None
            jq_code = self._to_jq_code(code, exchange=exchange)
            if jq_code and jq_code not in result:
                result.append(jq_code)
        return result

    def _fetch_index_stocks(
        self,
        index_symbol: str,
        date: Optional[Union[str, datetime]],
    ) -> List[str]:
        """调用 akshare 获取最新指数成分。"""
        _ = date
        ak = self._ensure_akshare()
        symbol = self._to_ak_symbol(index_symbol)
        for getter_name in ("index_stock_cons_csindex", "index_stock_cons"):
            getter = getattr(ak, getter_name, None)
            if not callable(getter):
                continue
            try:
                df = pd.DataFrame(getter(symbol=symbol))
            except Exception:
                continue
            codes = self._extract_index_codes(df)
            if codes:
                return codes
        return []

    def get_index_stocks(
        self,
        index_symbol: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> List[str]:
        """获取指数成分股；仅支持最新成分。"""
        kwargs = {"index_symbol": index_symbol, "date": date}
        return self._cache.cached_call(
            "get_index_stocks",
            kwargs,
            lambda _: self._fetch_index_stocks(index_symbol, date),
            result_type="list_str",
        )

    # ------------------------ 分红送配 ------------------------
    def _fetch_split_dividend(
        self,
        security: str,
        start_date: Optional[Union[str, datetime]],
        end_date: Optional[Union[str, datetime]],
    ) -> List[Dict[str, Any]]:
        """读取个股历史分红送配；仅支持股票代码。"""
        if self._infer_asset_kind(security) != "stock":
            return []
        ak = self._ensure_akshare()
        symbol = self._to_ak_symbol(security)
        try:
            raw = ak.stock_history_dividend_detail(symbol=symbol, indicator="分红")
        except Exception:
            return []
        df = pd.DataFrame(raw)
        if df.empty:
            return []
        date_col = self._pick_column(df, "除权除息日", "股权登记日", "公告日期")
        if date_col is None:
            return []
        start_ts = self._as_timestamp(start_date)
        end_ts = self._as_timestamp(end_date)
        result: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            event_ts = pd.to_datetime(row.get(date_col), errors="coerce")
            if pd.isna(event_ts):
                continue
            if start_ts is not None and event_ts.normalize() < start_ts.normalize():
                continue
            if end_ts is not None and event_ts.normalize() > end_ts.normalize():
                continue
            stock_paid = self._to_float(row.get("送股"))
            into_shares = self._to_float(row.get("转增"))
            bonus = self._to_float(row.get("派息"))
            result.append(
                {
                    "security": security,
                    "date": event_ts.date(),
                    "scale_factor": 1.0 + (stock_paid + into_shares) / 10.0,
                    "bonus_pre_tax": bonus,
                    "per_base": 10,
                }
            )
        return result

    def get_split_dividend(
        self,
        security: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        """获取个股分红送配事件（Beta，口径来自新浪财经）。"""
        kwargs = {"security": security, "start_date": start_date, "end_date": end_date}
        return self._cache.cached_call(
            "get_split_dividend",
            kwargs,
            lambda _: self._fetch_split_dividend(security, start_date, end_date),
            result_type="list_dict",
        )

    # ------------------------ 证券信息 ------------------------
    def get_security_info(
        self,
        security: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """返回证券基础信息；股票名称和上市时间来自东方财富。"""
        _ = date
        kind = self._infer_asset_kind(security)
        jq_type = self._infer_jq_security_type(security)
        category = "fund" if jq_type == "fund" else jq_type
        info: Dict[str, Any] = {
            "code": security,
            "display_name": str(security),
            "name": str(security),
            "start_date": Date(1990, 12, 19),
            "end_date": Date(2200, 1, 1),
            "type": jq_type,
            "category": category,
        }
        if kind != "stock":
            return info
        try:
            raw = self._ensure_akshare().stock_individual_info_em(
                symbol=self._to_ak_symbol(security)
            )
            df = pd.DataFrame(raw)
            if not df.empty and {"item", "value"}.issubset(df.columns):
                mapping = dict(zip(df["item"], df["value"]))
                name = mapping.get("股票简称")
                if name:
                    info["display_name"] = str(name)
                    info["name"] = str(name)
                industry = mapping.get("行业")
                if industry:
                    info["industry"] = str(industry)
                listing = mapping.get("上市时间")
                if listing is not None and not pd.isna(listing):
                    listing_text = str(listing).split(".")[0]
                    parsed = pd.to_datetime(listing_text, format="%Y%m%d", errors="coerce")
                    if pd.isna(parsed):
                        parsed = pd.to_datetime(listing_text, errors="coerce")
                    if not pd.isna(parsed):
                        info["start_date"] = parsed.date()
        except Exception:
            pass
        return info

    # ------------------------ 实时快照 ------------------------
    def _fetch_spot(self, security: str) -> Optional[pd.Series]:
        """读取单证券实时快照行。"""
        ak = self._ensure_akshare()
        kind = self._infer_asset_kind(security)
        symbol = self._to_ak_symbol(security)
        getters: List[Tuple[Any, Dict[str, Any]]] = []
        if kind == "stock":
            getters.append((getattr(ak, "stock_zh_a_spot_em", None), {}))
        elif kind == "etf":
            getters.append((getattr(ak, "fund_etf_spot_em", None), {}))
        elif kind == "lof":
            getters.append((getattr(ak, "fund_lof_spot_em", None), {}))
        else:
            getters.append(
                (getattr(ak, "stock_zh_index_spot_em", None), {"symbol": "沪深重要指数"})
            )
            getters.append((getattr(ak, "stock_zh_index_spot_sina", None), {}))
        for getter, kwargs in getters:
            if not callable(getter):
                continue
            try:
                df = pd.DataFrame(getter(**kwargs))
            except Exception:
                continue
            if df.empty:
                continue
            code_col = self._pick_column(df, "代码", "code")
            if code_col is None:
                continue
            codes = df[code_col].astype(str).str.zfill(6)
            matched = df[codes == symbol.zfill(6)]
            if not matched.empty:
                return matched.iloc[0]
        return None

    def get_current_tick(
        self,
        security: str,
        dt: Optional[Union[str, datetime]] = None,
        df: bool = False,
    ) -> Optional[Any]:
        """获取最新实时快照；非交易时段仍返回最近一次快照。"""
        row = self._fetch_spot(security)
        if row is None:
            return pd.DataFrame() if df else None
        last_price = self._to_float(row.get("最新价"))
        volume = self._to_float(row.get("成交量")) * 100.0
        tick = {
            "sid": security,
            "symbol": security,
            "last_price": last_price,
            "open": self._to_float(row.get("今开", row.get("开盘价"))),
            "high": self._to_float(row.get("最高", row.get("最高价"))),
            "low": self._to_float(row.get("最低", row.get("最低价"))),
            "volume": volume,
            "amount": self._to_float(row.get("成交额")),
            "pre_close": self._to_float(row.get("昨收")),
            "limit_up": 0.0,
            "limit_down": 0.0,
            "trading_status": 0 if last_price > 0 else 1,
            "paused": last_price <= 0,
            "dt": str(dt or datetime.now()),
            "provider": self.name,
        }
        return pd.DataFrame([tick]) if df else tick

    def get_live_current(self, security: str) -> Dict[str, Any]:
        """返回 LiveCurrentData 需要的实时行情字典。"""
        tick = self.get_current_tick(security)
        if not isinstance(tick, dict):
            return {}
        return {
            "last_price": self._to_float(tick.get("last_price")),
            "high_limit": self._to_float(tick.get("limit_up")),
            "low_limit": self._to_float(tick.get("limit_down")),
            "paused": bool(tick.get("paused")),
        }

    # ------------------------ 估值与财务 ------------------------
    @staticmethod
    def _report_periods() -> List[str]:
        """按当前日期推断最新已披露的报告期候选（从新到旧）。

        依据各报告期法定披露截止日: 三季报 10/31, 半年报 8/31, 一季报 4/30, 年报 4/30。
        """
        today = datetime.now()
        year, month = today.year, today.month
        if month >= 11:  # 三季报已披露完
            return [f"{year}0930", f"{year}0630", f"{year}0331", f"{year - 1}1231"]
        if month >= 9:  # 三季报披露中, 取已披露完的半年报
            return [f"{year}0630", f"{year}0331", f"{year - 1}1231"]
        if month >= 5:  # 半年报披露中, 取一季报
            return [f"{year}0331", f"{year - 1}1231"]
        return [f"{year - 1}1231", f"{year - 1}0930"]

    def _fetch_pb_pe_spot(self) -> pd.DataFrame:
        """拉取全市场 PB/PE 快照, 返回 index=6位代码, columns=[pb, pe]。"""
        ak = self._ensure_akshare()
        df = pd.DataFrame(ak.stock_zh_a_spot_em())
        if df.empty:
            return pd.DataFrame(columns=["pb", "pe"])
        code_col = self._pick_column(df, "代码", "code")
        pb_col = self._pick_column(df, "市净率")
        pe_col = self._pick_column(df, "市盈率-动态", "市盈率")
        if code_col is None or pb_col is None or pe_col is None:
            raise ValueError(f"实时行情缺少市净率/市盈率字段: {list(df.columns)}")
        result = pd.DataFrame(
            {
                "code": df[code_col].astype(str).str.zfill(6),
                "pb": pd.to_numeric(df[pb_col], errors="coerce"),
                "pe": pd.to_numeric(df[pe_col], errors="coerce"),
            }
        )
        return result.set_index("code")[["pb", "pe"]]

    def get_pb_pe_spot(self) -> pd.DataFrame:
        """获取全市场个股 PB/PE 快照; 指数为6位代码, 列为 pb/pe。"""
        return self._cache.cached_call(
            "get_pb_pe_spot",
            {},
            lambda _: self._fetch_pb_pe_spot(),
            result_type="df",
        )

    def _fetch_market_pb_percentile(self) -> float:
        """计算全市场中位数 PB 的历史分位 (0~100)。"""
        ak = self._ensure_akshare()
        df = pd.DataFrame(ak.stock_a_all_pb())
        if df.empty or "middlePB" not in df.columns:
            raise ValueError("全A市净率序列为空")
        series = pd.to_numeric(df["middlePB"], errors="coerce").dropna()
        if series.empty:
            raise ValueError("全A市净率序列无有效值")
        pb = float(series.iloc[-1])
        quantile_col = "quantileInAllHistoryMiddlePB"
        if quantile_col in df.columns:
            quantile = pd.to_numeric(df[quantile_col], errors="coerce").dropna()
            if not quantile.empty:
                return round(float(quantile.iloc[-1]) * 100, 1)
        return round(float((series <= pb).mean()) * 100, 1)

    def _fetch_market_pb_series(self) -> pd.DataFrame:
        """拉取全A中位数 PB 历史序列, 返回 date/middlePB 两列。"""
        ak = self._ensure_akshare()
        df = pd.DataFrame(ak.stock_a_all_pb())
        if df.empty or "date" not in df.columns or "middlePB" not in df.columns:
            raise ValueError("全A市净率历史序列缺少 date/middlePB 字段")
        result = df[["date", "middlePB"]].copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result["middlePB"] = pd.to_numeric(result["middlePB"], errors="coerce")
        return result.dropna(subset=["date", "middlePB"]).reset_index(drop=True)

    def get_market_pb_series(self) -> pd.DataFrame:
        """获取全A中位数 PB 历史序列, 返回 date/middlePB 两列。"""
        return self._cache.cached_call(
            "get_market_pb_series",
            {},
            lambda _: self._fetch_market_pb_series(),
            result_type="df",
        )

    def get_market_pb_percentile(self) -> float:
        """获取全市场 PB 历史分位 (0~100), 用于仓位管理。"""
        return self._cache.cached_call(
            "get_market_pb_percentile",
            {},
            lambda _: self._fetch_market_pb_percentile(),
            result_type="float",
        )

    def _fetch_financial_snapshot(self, period: str) -> Dict[str, Dict[str, Any]]:
        """按报告期拉取全市场业绩报表及策略所需每股指标。"""
        ak = self._ensure_akshare()
        df = pd.DataFrame(ak.stock_yjbb_em(date=period))
        if df.empty:
            return {}
        code_col = self._pick_column(df, "股票代码", "代码")
        name_col = self._pick_column(df, "股票简称", "证券简称", "名称")
        roe_col = self._pick_column(df, "净资产收益率")
        growth_col = self._pick_column(df, "营业总收入-同比增长")
        eps_col = self._pick_column(df, "每股收益")
        bvps_col = self._pick_column(df, "每股净资产")
        industry_col = self._pick_column(df, "所处行业")
        if any(
            col is None for col in (code_col, roe_col, growth_col, eps_col, bvps_col)
        ):
            raise ValueError(
                f"业绩报表缺少代码/ROE/营收增速/EPS/BVPS字段: {list(df.columns)}"
            )
        snapshot: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            code = self._to_ak_symbol(str(row.get(code_col) or "")).strip().zfill(6)
            if not code.isdigit():
                continue
            industry = row.get(industry_col) if industry_col else None
            if industry is not None and pd.isna(industry):
                industry = None
            snapshot[code] = {
                "name": (
                    ""
                    if name_col is None or pd.isna(row.get(name_col))
                    else str(row.get(name_col))
                ),
                "roe": self._to_float(row.get(roe_col)),
                "revenue_growth": self._to_float(row.get(growth_col)),
                "eps": self._to_float(row.get(eps_col)),
                "bvps": self._to_float(row.get(bvps_col)),
                "industry": "" if industry is None else str(industry),
            }
        return snapshot

    def get_financial_snapshot(
        self,
        codes: Optional[Union[str, Sequence[str]]] = None,
        date: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """获取全市场财务快照 (名称/ROE/营收增速/EPS/BVPS/行业)。
        codes 非空时按代码过滤。

        date 指定报告期 (如 "20260930"); 默认按披露进度推断最新报告期,
        指定报告期无数据时逐级回退到更早的报告期。
        """
        wanted: Optional[set] = None
        if codes:
            wanted = {self._to_ak_symbol(item).strip().zfill(6) for item in self._as_list(codes)}
        periods = [str(date)] if date else self._report_periods()
        for period in periods:
            snapshot = self._cache.cached_call(
                # Version the cache key because this snapshot now includes EPS/BVPS/name.
                "get_financial_snapshot_v2",
                {"date": period},
                lambda _: self._fetch_financial_snapshot(period),
                result_type="list_dict",
            )
            if not snapshot:
                continue
            if wanted is not None:
                snapshot = {c: v for c, v in snapshot.items() if c in wanted}
            if snapshot:
                return snapshot
        return {}
