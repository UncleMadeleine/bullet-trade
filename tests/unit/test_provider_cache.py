"""Provider 磁盘缓存：目录结构、命中与历史区间永久缓存。"""

from __future__ import annotations

import pandas as pd

from bullet_trade.data.cache import CacheManager


def test_env_cache_dir_has_single_provider_level(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_CACHE_DIR", str(tmp_path))
    cache = CacheManager("akshare")
    calls = []

    def fetch(_kwargs):
        calls.append(1)
        return pd.DataFrame({"value": [1.0]})

    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")
    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")

    assert len(calls) == 1
    method_dir = tmp_path / "akshare" / "demo"
    assert method_dir.is_dir()
    assert not (tmp_path / "akshare" / "akshare").exists()
    assert list(method_dir.glob("*.meta.json"))


def test_explicit_cache_dir_still_gets_provider_subdir(tmp_path):
    cache = CacheManager("akshare", cache_dir=str(tmp_path / "custom"))
    calls = []

    def fetch(_kwargs):
        calls.append(1)
        return pd.DataFrame({"value": [2.0]})

    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")
    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")

    assert len(calls) == 1
    assert (tmp_path / "custom" / "akshare" / "demo").is_dir()


def test_provider_suffixed_cache_dir_is_not_duplicated(tmp_path):
    # env_loader 会传 DATA_CACHE_DIR/akshare，这里不能再拼一层 akshare。
    cache = CacheManager("akshare", cache_dir=str(tmp_path / "akshare"))
    calls = []

    def fetch(_kwargs):
        calls.append(1)
        return pd.DataFrame({"value": [3.0]})

    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")
    cache.cached_call("demo", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, fetch, "df")

    assert len(calls) == 1
    assert (tmp_path / "akshare" / "demo").is_dir()
    assert not (tmp_path / "akshare" / "akshare").exists()
