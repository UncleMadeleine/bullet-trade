# 回测数据会话优化

回测数据会话是一次回测运行内的临时性能优化层。它默认关闭，只在回测入口显式启用后生效，不会写入永久行情缓存，也不会改变实盘或 QMT 服务端的数据刷新逻辑。

## 启用方式

命令行启用:

```bash
bullet-trade backtest strategy.py \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --backtest-data-session \
  --backtest-data-session-manifest backtest_results/session_manifest.json
```

可选启用内存行情块缓存:

```bash
bullet-trade backtest strategy.py \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --backtest-data-session \
  --backtest-price-block-cache
```

也可以使用环境变量:

```bash
export BT_BACKTEST_DATA_SESSION=true
export BT_BACKTEST_DATA_SESSION_QMT_DEDUP=true
export BT_BACKTEST_DATA_SESSION_PRICE_BLOCKS=false
export BT_BACKTEST_DATA_SESSION_MAX_BYTES=536870912
export BT_BACKTEST_DATA_SESSION_MIN_FREE_BYTES=1073741824
export BT_BACKTEST_DATA_SESSION_MANIFEST=backtest_results/session_manifest.json
```

## 能力边界

- MiniQMT 回测下载去重: 在回测 session 内按证券、周期和覆盖区间登记已下载数据，后续覆盖范围内的请求跳过 `download_history_data`。
- 内存行情块缓存: 仅处理可证明等价的单证券 `count` 历史窗口；`use_real_price=True` 的动态前复权不会缓存已锚定后的价格，而是缓存真实价格和复权因子等基础输入，再按当前 `pre_factor_ref_date` 重锚切片。不能证明等价的参数组合会自动降级到原 provider 路径。
- MiniQMT 本地数据块缓存: 启用 `--backtest-price-block-cache` 后，`mode=backtest` 的 MiniQMTProvider 会把本次回测覆盖区间内的 `xt.get_local_data` 结果按证券、周期和 `dividend_type` 暂存到内存，再按当前请求切片；动态前复权仍使用当前 `pre_factor_ref_date` 重新锚定，不复用已经锚定后的结果。
- current data 快照: 同一 bar 内可复用当前行情对象，进入下一 bar 后自动失效。
- 内存预算: 通过 `BT_BACKTEST_DATA_SESSION_MAX_BYTES` 设置硬上限；可选 `BT_BACKTEST_DATA_SESSION_MIN_FREE_BYTES` 保护系统剩余内存。

## 实盘隔离

该优化只在 `BacktestEngine.run()` 激活的回测上下文中有效。MiniQMT provider 还会检查自身 `mode`，只有 `mode=backtest` 才会使用下载去重和本地数据块缓存。`mode=live`、QMT server adapter、实时 tick、订阅行情和实盘 current data 都不会读取回测 session 的 downloaded 记录或内存缓存。

如果怀疑优化影响结果，可关闭:

```bash
unset BT_BACKTEST_DATA_SESSION
```

或不要传 `--backtest-data-session`。关闭后回测会回到原 provider 调用路径。

## Manifest

启用 manifest 后，回测结束会输出 JSON 文件，包含:

- 本次 session 的启用配置和内存预算。
- QMT 下载、跳过下载、覆盖校验和耗时。
- 内存缓存命中、穿透、驱逐、降级和峰值占用。
- current bar 快照命中和写入次数。

manifest 不包含账号、密钥、内部服务器或用户本地敏感路径。
