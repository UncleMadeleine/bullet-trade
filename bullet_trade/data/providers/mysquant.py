from __future__ import annotations

import os
import logging
from datetime import datetime, date as Date, timedelta, time as Time
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import pandas as pd

try:
    from typing import override
except ImportError:
    from typing_extensions import override  # type: ignore[assignment]

from .base import DataProvider
from ..cache import CacheManager

try:
    import gm.api as gm  # pyright: ignore[reportMissingImports]
except ImportError as exc:
    raise ImportError(
        "未安装掘金量化 SDK，请执行 `pip install bullet-trade[mysquant]` 或 `pip install gm-sdk`"
    ) from exc

logger = logging.getLogger(__name__)


class MysQuantProvider(DataProvider):
    """
    掘金量化 (MySQant) 数据源提供者。

    支持历史行情、实时快照、基础信息等。
    需要配置 MYSQUANT_TOKEN 环境变量或通过 config 传入。
    """

    name: str = "mysquant"
    requires_live_data: bool = True

    # Mapping: 掘金交易所 -> JQ 后缀
    _EXCHANGE_TO_JQ = {"SHSE": "XSHG", "SZSE": "XSHE", "BJSE": "BJ", "BSE": "BJ"}
    _JQ_TO_EXCHANGE = {"XSHG": "SHSE", "XSHE": "SZSE", "BJ": "SHSE"}

    # 默认价格字段
    _DEFAULT_PRICE_FIELDS = ["open", "close", "high", "low", "volume", "amount"]

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._token = (
            self.config.get("token")
            or os.getenv("MYSQUANT_TOKEN")
            or os.getenv("MYQUANT_TOKEN")
        )
        cache_dir_set = "cache_dir" in self.config
        cache_dir = self.config.get("cache_dir")
        self._cache = CacheManager(
            provider_name=self.name,
            cache_dir=cache_dir,
            fallback_to_env=not cache_dir_set,
        )
        self._security_info_cache: Dict[Any, Dict[str, Any]] = {}
        self._auth_done = False

    # ------------------------ 公共工具 ------------------------

    @classmethod
    def _to_mysquant_code(cls, security: str) -> str:
        """将代码转换为掘金格式（例如 600000.XSHG -> SHSE.600000）。幂等。"""
        if not security or "." not in security:
            return security
        code, suffix = security.split(".", 1)
        # 后缀不是 JQ 后缀（XSHG/XSHE/BJ）→ 已是掘金格式，直接返回
        if suffix.upper() not in {"XSHG", "XSHE", "BJ", "BSE"}:
            return security
        exchange = cls._JQ_TO_EXCHANGE.get(suffix.upper(), "SHSE")
        return f"{exchange}.{code}"

    @classmethod
    def _to_jq_code(cls, security: str) -> str:
        """将代码转换为 JQ 格式（例如 SHSE.600000 -> 600000.XSHG）。幂等。"""
        if not security or "." not in security:
            return security
        exchange, code = security.split(".", 1)
        # 前缀不是掘金交易所代码（SHSE/SZSE/BJSE/BSE）→ 已是 JQ 格式，直接返回
        if exchange.upper() not in cls._EXCHANGE_TO_JQ:
            return security
        jq_suffix = cls._EXCHANGE_TO_JQ.get(exchange.upper(), "XSHG")
        return f"{code}.{jq_suffix}"

    @staticmethod
    def _ensure_sdk() -> Any:
        """返回已导入的 gm.api 模块（模块级已导入，此处直接返回）。"""
        return gm

    def _ensure_auth(self) -> None:
        """确保认证已完成，否则触发 auth()。"""
        if not self._auth_done:
            self.auth()
        if not self._auth_done:
            raise RuntimeError("MysQuantProvider 未认证，请先调用 auth()")

    @staticmethod
    def _to_datetime_str(value: Optional[Union[str, datetime, Date]]) -> Optional[str]:
        """将日期时间转换为 YYYY-MM-DD HH:MM:SS 字符串。"""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return value
        try:
            return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_date_str(value: Optional[Union[str, datetime, Date]]) -> Optional[str]:
        """将日期转换为 YYYY-MM-DD 字符串。"""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return pd.to_datetime(value).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                return value
        try:
            return pd.to_datetime(value).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _normalize_frequency(self, frequency: str) -> str:
        """将 BulletTrade 频率映射到掘金支持的频率字符串。"""
        freq = frequency.lower()
        if freq in ("daily", "1d", "d"):
            return "1d"
        if freq in ("minute", "1m", "m1"):
            return "60s"
        if freq.endswith("m") and freq[:-1].isdigit():
            minutes = int(freq[:-1])
            minute_to_sec = {1: "60s", 5: "300s", 15: "900s", 30: "1800s", 60: "3600s"}
            return minute_to_sec.get(minutes, "1d")
        if freq.endswith("s") and freq[:-1].isdigit():
            seconds = int(freq[:-1])
            return f"{seconds}s"
        return "1d"

    def _adjust_to_gm(self, fq: str) -> int:
        """将复权参数映射为掘金常量。"""
        if fq == "pre":
            return gm.ADJUST_PREV
        if fq == "post":
            return gm.ADJUST_POST
        return gm.ADJUST_NONE

    # ------------------------ 认证 ------------------------

    def auth(
        self,
        user: Optional[str] = None,
        pwd: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        掘金量化认证。

        配置项：
        - token: 通过环境变量 MYSQUANT_TOKEN 或 config['token'] 传入
        - host/port: 可选，连接自定义终端地址
        """
        token = user or self._token
        if not token:
            raise RuntimeError(
                "MYSQUANT_TOKEN 未配置，"
                "请设置环境变量 MYSQUANT_TOKEN 或在 config 中传入 token"
            )
        gm.set_token(token)
        if host:
            gm.set_endpoint(host, port or 7070)
        self._auth_done = True

    # ------------------------ K 线数据 ------------------------

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
        fill_paused: bool = True,  # 保留以兼容接口，掘金使用 skip_suspended
        pre_factor_ref_date: Optional[Union[str, datetime]] = None,
        prefer_engine: bool = False,
        force_no_engine: bool = False,
    ) -> pd.DataFrame:
        self._ensure_auth()

        securities = security if isinstance(security, (list, tuple)) else [security]
        gm_freq = self._normalize_frequency(frequency)
        adjust = self._adjust_to_gm(fq)

        if fields is None:
            fields = list(self._DEFAULT_PRICE_FIELDS)
        fields_str = ",".join(fields) if fields else None

        start_str = self._to_datetime_str(start_date)
        end_str = self._to_datetime_str(end_date)

        frames: Dict[str, pd.DataFrame] = {}

        for sec in securities:
            mys_code = self._to_mysquant_code(sec)

            def _fetch_single(kw: Dict[str, Any]) -> pd.DataFrame:
                if kw.get("count") is not None:
                    df = gm.history_n(
                        symbol=kw["symbol"],
                        frequency=kw["frequency"],
                        count=kw["count"],
                        end_time=kw.get("end_time"),
                        fields=kw["fields"],
                        adjust=kw["adjust"],
                        skip_suspended=kw.get("skip_paused", False),
                        df=True,
                    )
                else:
                    df = gm.history(
                        symbol=kw["symbol"],
                        frequency=kw["frequency"],
                        start_time=kw.get("start_time"),
                        end_time=kw.get("end_time"),
                        fields=kw["fields"],
                        adjust=kw["adjust"],
                        skip_suspended=kw.get("skip_paused", False),
                        df=True,
                    )
                if df is None or df.empty:
                    return pd.DataFrame()
                return self._convert_price_df(df)

            kwargs = {
                "symbol": mys_code,
                "frequency": gm_freq,
                "start_time": start_str,
                "end_time": end_str,
                "count": count,
                "fields": fields_str,
                "adjust": adjust,
                "skip_paused": skip_paused,
            }

            frames[sec] = cast(
                pd.DataFrame,
                self._cache.cached_call("get_price", kwargs, _fetch_single, result_type="df")
            )

        if len(frames) == 1:
            return next(iter(frames.values()))

        if panel:
            concatenated = pd.concat(frames, axis=1)
            return cast(pd.DataFrame, concatenated)

        long_rows = []
        for sec, df in frames.items():
            tmp = df.copy()
            tmp["code"] = sec
            long_rows.append(tmp)
        merged = pd.concat(long_rows, axis=0)
        return cast(pd.DataFrame, merged)

    def _convert_price_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """将掘金返回的 DataFrame 转换为 BulletTrade 标准格式。"""
        if df.empty:
            return df
        result = df.copy()
        column_mapping = {
            "eob": "time",
            "close": "close",
            "open": "open",
            "high": "high",
            "low": "low",
            "volume": "volume",
            "amount": "money",
        }
        result.rename(columns=column_mapping, inplace=True, errors="ignore")
        if "time" in result.columns:
            result["time"] = pd.to_datetime(result["time"])
            result.set_index("time", inplace=True)
        standard_cols = ["open", "close", "high", "low", "volume", "money"]
        available = [c for c in standard_cols if c in result.columns]
        result = cast(pd.DataFrame, result[available])
        return result

    # ------------------------ 交易日 ------------------------

    @override
    def get_bars(self, security: Union[str, List[str]], count: int, unit: str = '1d',
                fields: Optional[List[str]] = None, include_now: bool = False,
                end_dt: Optional[Union[str, datetime]] = None, fq_ref_date: Union[int, datetime] = 1,
                df: bool = False) -> Any:
        """
        获取K线数据（聚宽风格）。通过 gm.history() 实现。

        Args:
            security: 标的代码（可字符串或列表）
            count: 获取的bar数量（从end_dt往前推）
            unit: 频率 - '1d', '1m', '5m', '15m', '30m', '60m' 等
            fields: 需要的字段列表
            include_now: 是否包含不完整的当前bar（掘金默认包含）
            end_dt: 结束时间
            fq_ref_date: 复权基准日（1=最新交易日，或指定datetime）
            df: 是否返回DataFrame（False则返回list/dict）

        Returns:
            DataFrame 或 list（取决于 df 参数）
        """
        self._ensure_auth()
        gm_module = self._ensure_sdk()

        # 处理证券代码
        securities = [security] if isinstance(security, str) else list(security)
        mys_codes = [self._to_mysquant_code(s) for s in securities]

        # 频率映射：聚宽 → 掘金
        # 聚宽: '1d', '1m', '5m', '15m', '30m', '60m'
        # 掘金: '1d', '60s', '300s', '900s', '1800s', '3600s'
        unit_normalized = unit.lower().strip()
        freq_map = {
            '1d': '1d',
            'daily': '1d',
            'd': '1d',
            '1m': '60s',
            'minute': '60s',
            'm': '60s',
            '5m': '300s',
            '15m': '900s',
            '30m': '1800s',
            '60m': '3600s',
        }
        gm_freq = freq_map.get(unit_normalized, unit_normalized)

        # 处理复权参数
        adjust_mode = gm.ADJUST_PREV  # 默认前复权
        if fq_ref_date == 1:
            # 使用最新交易日作为复权基准
            adjust_mode = gm.ADJUST_PREV
        elif isinstance(fq_ref_date, (int, float)) and fq_ref_date == 0:
            adjust_mode = gm.ADJUST_NONE
        # 注意：掘金没有"后复权"概念，只有不复权/前复权

        # 确定 end_dt（统一转换为 datetime）
        if end_dt is None:
            end_dt = datetime.now()
        elif isinstance(end_dt, datetime):
            pass  # already datetime
        elif isinstance(end_dt, Date):
            end_dt = datetime.combine(end_dt, Time.min)
        else:
            end_dt = pd.to_datetime(end_dt).to_pydatetime()

        # 类型收窄：各分支已覆盖所有可能，end_dt 此时必为 datetime
        end_dt = cast(datetime, end_dt)

        # 计算 start_dt：根据 count 和频率推算
        # 注意：掘金 history() 需要 start_date 和 end_date，或者 count
        # 我们使用 count 参数，掘金会返回最近 count 个bar
        # 但掘金的 count 行为可能与聚宽略有差异，需测试验证

        # 字段映射
        # 聚宽字段: date, open, close, high, low, volume, money
        # 掘金字段: eob, open, close, high, low, volume, amount
        field_map = {
            'date': 'eob',
            'money': 'amount',
        }
        gm_fields = []
        if fields:
            for f in fields:
                gm_fields.append(field_map.get(f, f))
        else:
            gm_fields = ['eob', 'open', 'close', 'high', 'low', 'volume', 'amount']

        # 调用 gm.history
        all_frames = {}
        for code in mys_codes:
            try:
                df_raw = gm_module.history(
                    symbol=code,
                    frequency=gm_freq,
                    start=end_dt - timedelta(days=count * 2),  # 宽泛估算，用count取
                    end=end_dt,
                    adjust=adjust_mode,
                    fields=gm_fields,
                    count=count,
                    # 注意：掘金 history 的 count 是最新bar数量
                )
                if df_raw is not None and not df_raw.empty:
                    # 重命名字段回聚宽风格
                    reverse_map = {v: k for k, v in field_map.items()}
                    df_raw = df_raw.rename(columns=reverse_map, errors='ignore')

                    # 确保必要字段存在
                    if 'date' in df_raw.columns:
                        df_raw['date'] = pd.to_datetime(df_raw['date'])
                        df_raw.set_index('date', inplace=True)
                    # 标准化字段
                    for std_field in ['open', 'close', 'high', 'low', 'volume', 'money']:
                        if std_field not in df_raw.columns:
                            df_raw[std_field] = 0.0
                    all_frames[code] = df_raw
            except Exception as e:
                logger.debug(f"gm.history 获取 {code} 数据失败: {e}")
                all_frames[code] = pd.DataFrame()

        # 组装结果
        if len(all_frames) == 1:
            result_df = next(iter(all_frames.values()))
        else:
            # 多标的：panel 模式
            if df:
                # 返回多列 DataFrame (panel=False 实际是 long 格式)
                # 按聚宽习惯：panel=True 返回 3D，但这里 df=False 时我们才返回 long
                # 简化：多标的一律返回 long 格式（含 code 列）
                long_frames = []
                for sec, df_sec in all_frames.items():
                    tmp = df_sec.copy()
                    tmp['code'] = self._to_jq_code(sec)
                    long_frames.append(tmp)
                result_df = pd.concat(long_frames, axis=0) if long_frames else pd.DataFrame()
            else:
                # panel=True (默认) → 返回 DataFrame，列=security
                result_df = pd.concat(all_frames, axis=1)

        # 按 count 截断
        if count and not result_df.empty:
            result_df = result_df.tail(count)

        # 如果只需要原始 dict/list（df=False 且不是多标的长格式）
        if not df and len(all_frames) == 1:
            # 返回 list[dict] 格式，每行一个bar
            df_single = next(iter(all_frames.values()))
            if df_single.empty:
                return []
            return df_single.reset_index().to_dict('records')

        return result_df

    @override
    def get_ticks(self, security: str, end_dt: Union[str, datetime],
                 start_dt: Optional[Union[str, datetime]] = None,
                 count: Optional[int] = None, fields: Optional[List[str]] = None,
                 skip: bool = False, df: bool = False) -> Any:
        """
        获取Tick历史数据（聚宽风格）。
        注意：掘金 SDK 的 current() 仅支持获取当前快照，不支持历史Tick查询。
        此方法仅返回当前时刻的tick（类似 get_current_tick），历史查询将抛出 NotImplementedError。

        Args:
            security: 标的代码
            end_dt: 结束时间（被忽略，仅返回当前）
            start_dt: 开始时间（被忽略）
            count: 数量（被忽略）
            fields: 字段列表（被忽略）
            skip: 是否跳过（被忽略）
            df: 是否返回DataFrame

        Returns:
            当前tick数据
        """
        # 掘金不支持历史tick查询，current() 只返回当前快照
        # 如果用户传入了 start_dt 或 count，说明需要历史数据 → 报错
        if start_dt is not None or count is not None:
            raise NotImplementedError("掘金量化 SDK 不支持历史Tick数据查询，仅支持当前快照。请使用 get_current_tick() 或 get_live_current()。")

        # 直接返回当前快照
        return self.get_current_tick(security, dt=end_dt, df=df)

    def get_trade_days(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        count: Optional[int] = None,
    ) -> List[datetime]:
        self._ensure_auth()

        start_str = self._to_date_str(start_date)
        end_str = self._to_date_str(end_date)

        def _fetch(kw: Dict[str, Any]) -> List[datetime]:
            gm_module = self._ensure_sdk()
            calendar = gm_module.get_trading_calendar(
                exchange="SHSE",
                start_date=kw.get("start_date"),
                end_date=kw.get("end_date"),
            )
            if not calendar:
                return []
            days = [pd.to_datetime(d).to_pydatetime() for d in calendar]
            if kw.get("count") and kw["count"] > 0:
                days = days[-kw["count"]:]
            return days

        kwargs = {"start_date": start_str, "end_date": end_str, "count": count}

        date_strs = self._cache.cached_call(
            "get_trade_days", kwargs, _fetch, result_type="list_date"
        )
        return cast(List[datetime], date_strs)

    # ------------------------ 证券信息 ------------------------

    def get_all_securities(
        self,
        types: Union[str, List[str]] = "stock",
        date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        self._ensure_auth()

        if isinstance(types, str):
            types = [types]

        target_date = self._to_date_str(date) if date else None
        target_dt = pd.to_datetime(target_date) if target_date else None

        kwargs = {"types": tuple(sorted(types)), "date": target_date}

        def _fetch(kw: Dict[str, Any]) -> Dict[str, Any]:
            gm_module = self._ensure_sdk()
            results: Dict[str, Any] = {}
            query_date = kw.get("date")
            query_dt = pd.to_datetime(query_date) if query_date else None

            for t in kw["types"]:
                sec_type1 = None
                exchanges = None

                if t == "stock":
                    sec_type1 = gm.SEC_TYPE_STOCK
                    exchanges = ["SHSE", "SZSE"]
                elif t == "fund":
                    sec_type1 = gm.SEC_TYPE_FUND
                elif t == "etf":
                    sec_type1 = gm.SEC_TYPE_FUND
                elif t == "index":
                    sec_type1 = gm.SEC_TYPE_INDEX
                else:
                    continue

                symbols = gm_module.get_symbol_infos(
                    sec_type1=sec_type1,
                    sec_type2=None,
                    exchanges=exchanges,
                    df=False,
                )

                for sym_info in symbols:
                    sym = sym_info.get("symbol", "")
                    jq_code = self._to_jq_code(sym)
                    listed_str = sym_info.get("listed_date")
                    delisted_str = sym_info.get("delisted_date")
                    listed_dt = pd.to_datetime(listed_str) if listed_str else None
                    delisted_dt = (
                        pd.to_datetime(delisted_str) if delisted_str else None
                    )

                    if query_dt is not None:
                        if listed_dt and query_dt < listed_dt:
                            continue
                        if delisted_dt and query_dt > delisted_dt:
                            continue

                    results[jq_code] = {
                        "display_name": sym_info.get("name", sym),
                        "name": sym_info.get("name", sym),
                        "start_date": listed_dt,
                        "end_date": delisted_dt,
                        "type": t,
                        "subtype": sym_info.get("sec_type2"),
                    }

            return results

        data = self._cache.cached_call(
            "get_all_securities", kwargs, _fetch, result_type="list_dict"
        )
        if not data:
            return pd.DataFrame(columns=["display_name", "name", "start_date", "end_date", "type"])

        df = pd.DataFrame.from_dict(cast(Dict[str, Any], data), orient="index")
        # type: ignore[assignment]
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
        # type: ignore[assignment]
        df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
        return df

    # ------------------------ 指数成分股 ------------------------

    def get_index_stocks(
        self, index_symbol: str, date: Optional[Union[str, datetime]] = None
    ) -> List[str]:
        self._ensure_auth()

        gm_index = self._to_mysquant_code(index_symbol)
        target_date = self._to_date_str(date) if date else None

        kwargs = {"index": gm_index, "date": target_date}

        def _fetch(kw: Dict[str, Any]) -> List[str]:
            gm_module = self._ensure_sdk()
            df = gm_module.stk_get_index_constituents(
                index=kw["index"], trade_date=kw.get("date")
            )
            if df is None or df.empty:
                return []
            # type: ignore[attr-defined]
            symbols = cast(List[str], df["symbol"].tolist())
            return [self._to_jq_code(s) for s in symbols]

        return cast(List[str], self._cache.cached_call(
            "get_index_stocks", kwargs, _fetch, result_type="list_str"
        ))

    # ------------------------ 证券信息 ------------------------

    def get_security_info(
        self,
        security: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        cache_key = (security, date) if date is not None else (security, None)
        cached = self._security_info_cache.get(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Any] = {"code": security}

        try:
            df = self.get_all_securities(
                types=["stock", "fund", "etf", "index"], date=date
            )
            if not df.empty and security in df.index:
                row = df.loc[security]
                # type: ignore[union-attr]
                display = row.get("display_name") if hasattr(row, "get") else row.get("display_name", security)
                name_val = row.get("name") if hasattr(row, "get") else row.get("name", security)
                start_val = row.get("start_date")
                end_val = row.get("end_date")
                type_val = row.get("type") if hasattr(row, "get") else row.get("type", "stock")
                subtype_val = row.get("subtype") if hasattr(row, "get") else row.get("subtype")

                result.update(
                    {
                        "display_name": display if display is not None else security,
                        "name": name_val if name_val is not None else security,
                        "start_date": start_val,
                        "end_date": end_val,
                        "type": type_val,
                        "subtype": subtype_val,
                    }
                )
        except Exception as e:
            logger.debug(f"获取 {security} 基本信息失败: {e}")
            # 即使失败也返回基本结构

        self._security_info_cache[cache_key] = result
        return result

    # ------------------------ 分红/拆分 ------------------------

    def get_split_dividend(
        self,
        security: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_auth()

        mys_code = self._to_mysquant_code(security)
        start_str = self._to_date_str(start_date)
        end_str = self._to_date_str(end_date)

        kwargs = {"security": mys_code, "start_date": start_str, "end_date": end_str}

        def _fetch(kw: Dict[str, Any]) -> List[Dict[str, Any]]:
            gm_module = self._ensure_sdk()
            try:
                df = gm_module.stk_get_dividend(
                    symbol=kw["security"],
                    start_date=kw.get("start_date"),
                    end_date=kw.get("end_date"),
                )
            except (AttributeError, ValueError, TypeError, RuntimeError):
                return []

            if df is None or df.empty:
                return []

            events: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                ex_date = row.get("ex_date")
                # 确保数值不为 None 再转换为 float
                bonus_raw = row.get("bonus_ratio_rmb")
                stock_div_raw = row.get("stock_dividend_ratio")
                transfer_raw = row.get("transfer_ratio")

                bonus_rmb = float(bonus_raw) if bonus_raw is not None else 0.0  # type: ignore[arg-type]
                stock_dividend_ratio = float(stock_div_raw) if stock_div_raw is not None else 0.0  # type: ignore[arg-type]
                transfer_ratio = float(transfer_raw) if transfer_raw is not None else 0.0  # type: ignore[arg-type]

                per_base = 10
                stock_paid = stock_dividend_ratio
                transfer = transfer_ratio
                scale_factor = 1.0 + (stock_paid + transfer) / per_base

                event_date = pd.to_datetime(ex_date) if ex_date is not None else None
                events.append(
                    {
                        "security": security,
                        "date": event_date,
                        "security_type": "stock",
                        "scale_factor": scale_factor,
                        "bonus_pre_tax": bonus_rmb,
                        "per_base": per_base,
                    }
                )

            return events

        return cast(List[Dict[str, Any]], self._cache.cached_call(
            "get_split_dividend", kwargs, _fetch, result_type="list_dict"
        ))

    # ------------------------ 实时行情 ------------------------

    def get_current_tick(
        self,
        security: str,
        dt: Optional[Union[str, datetime]] = None,
        df: bool = False,
    ) -> Any:
        self._ensure_auth()
        mys_code = self._to_mysquant_code(security)

        try:
            gm_module = self._ensure_sdk()
            tick_data = gm_module.current(symbols=mys_code, df=False)
            if not tick_data:
                return pd.DataFrame() if df else None
            if isinstance(tick_data, list):
                tick = tick_data[0] if tick_data else None
            else:
                tick = tick_data
            if tick is None:
                return pd.DataFrame() if df else None
            if df:
                # Ensure tick is a dict before creating DataFrame
                if isinstance(tick, dict):
                    return pd.DataFrame([tick])
                return pd.DataFrame()
            return tick  # type: ignore[return-value]
        except Exception as e:
            logger.debug(f"获取 {security} 当前行情失败: {e}")
            return pd.DataFrame() if df else None

    def get_live_current(self, security: str) -> Dict[str, Any]:
        """
        返回实盘当前快照（最小字段）。
        返回字段：
        - last_price: 当前价
        - high_limit: 当日涨跌停价
        - low_limit: 当日涨跌停价
        - paused: 是否停牌
        """
        try:
            tick = self.get_current_tick(security)
            if not tick:
                return {}

            last_price = tick.get("last_price", tick.get("close"))
            if last_price is None:
                last_price = 0.0

            high_limit = tick.get("high_limit")
            if high_limit is None:
                high_limit = 0.0

            low_limit = tick.get("low_limit")
            if low_limit is None:
                low_limit = 0.0

            volume = tick.get("volume", 1)
            paused = bool(volume == 0)

            return {
                "last_price": float(last_price),  # type: ignore[arg-type]
                "high_limit": float(high_limit),  # type: ignore[arg-type]
                "low_limit": float(low_limit),  # type: ignore[arg-type]
                "paused": paused,
            }
        except Exception as e:
            logger.debug(f"获取 {security} 实时快照失败: {e}")
            return {}
