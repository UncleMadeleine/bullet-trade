# AKShare 免费数据源 (Beta)

`AkshareProvider` 位于 `bullet_trade/data/providers/akshare.py`，通过 `DEFAULT_DATA_PROVIDER=akshare` 或 `set_data_provider("akshare")` 激活。`ak` 是兼容别名。

AKShare 聚合东方财富、新浪财经、中证指数等公开网页数据，不需要账号或 token，适合免费行情探索、轻量回测和教学场景。它属于 **Beta/补充数据源**，不建议替代 JQData、MiniQMT 或已验证的 Tushare 作为生产主源。

## 安装与启用

```bash
pip install bullet-trade[akshare]
# 或
pip install akshare
```

```env
DEFAULT_DATA_PROVIDER=akshare
# 可选：开启历史行情缓存
DATA_CACHE_DIR=~/.bullet-trade/cache
```

```python
from bullet_trade import set_data_provider, get_price

set_data_provider("akshare")
df = get_price("000001.XSHE", start_date="2024-01-01", end_date="2024-12-31")
print(df.head())
```

## 代码格式

对外统一使用聚宽格式：

- `000001.XSHE`、`600000.XSHG`
- `000300.XSHG`（指数）
- `510300.XSHG`（ETF）、`161725.XSHE`（LOF）

Provider 内部会转换为 AKShare 接口常用的 6 位代码。也兼容 `SH`/`SZ` 后缀和少量市场前缀。

## 已支持能力

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| A 股日线 | `stock_zh_a_hist` | 支持 `daily`/`weekly`/`monthly`，支持 qfq/hfq |
| A 股分钟线 | `stock_zh_a_hist_min_em` | 支持 1/5/15/30/60 分钟，历史深度由东方财富决定 |
| 指数行情 | `index_zh_a_hist` / `index_zh_a_hist_min_em` | 日线和分钟线 |
| ETF/LOF 行情 | `fund_etf_hist_em` / `fund_lof_hist_em` 等 | 日线和分钟线 |
| 交易日 | `tool_trade_date_hist_sina` | 支持区间和 `count` |
| 证券列表 | `stock_info_a_code_name`、`fund_etf_spot_em`、`fund_lof_spot_em`、`index_stock_info` | 仅当前快照 |
| 指数成分 | `index_stock_cons_csindex`，失败回退 `index_stock_cons` | 仅最新成分 |
| 分红送配 | `stock_history_dividend_detail` | 仅股票，字段来自新浪财经 |
| 证券信息 | `stock_individual_info_em` | 股票简称、行业、上市时间 |
| 实时快照 | `stock_zh_a_spot_em`、ETF/LOF/指数现货接口 | 轮询式快照，非订阅推送 |

## 字段与单位

- `time`：统一转换为 `pandas.Timestamp` 索引。
- `open`/`close`/`high`/`low`：原始价格。
- `volume`：统一为 **股**（AKShare 成交量原始单位为手，Provider 已乘以 100）。
- `money`：成交额，单位元。
- `paused`：AKShare 不提供停牌标记，历史行情默认 `False`。
- `high_limit`/`low_limit`：AKShare 不提供，返回 `0.0`，由上层规则在需要时兜底。
- `factor`：固定返回 `1.0`。

## 复权说明

- `fq="pre"` 映射为 `qfq`，`fq="post"` 映射为 `hfq`，`fq="none"` 返回不复权数据。
- AKShare 的前复权以接口最新价格为锚点，**不支持** `pre_factor_ref_date` 的按历史日期动态锚定。
- 需要精确真实价格回测时，请使用 JQData、MiniQMT 或已验证的 Tushare。

## 已知限制

1. **没有历史时点数据**：`get_all_securities(date)` 和 `get_index_stocks(date)` 只能返回当前结果，回测存在幸存者偏差。
2. **分钟历史浅**：1 分钟通常只有最近几个交易日，长周期分钟回测不可用。
3. **无 tick 历史**：不实现 `get_ticks`；实时场景使用 `get_current_tick`/`get_live_current`。
4. **无停牌和涨跌停字段**：停牌日会被数据源直接省略，涨跌停价返回 0，由上层规则兜底。
5. **依赖公开网页接口**：AKShare 升级或上游页面改版可能导致接口失效；建议锁定版本并在策略侧处理异常。
6. **不支持财务、行业、概念、龙虎榜等扩展接口**：这些方法会返回空或抛出未实现错误。

## 与 JQData 的差异

| 特性 | JQData | AKShare |
| --- | --- | --- |
| 账号 | 需要账号/权限 | 不需要 |
| 历史时点证券列表 | 支持 | 仅当前 |
| 指数历史成分 | 支持 | 仅最新 |
| 分钟历史深度 | 取决于权限 | 免费接口较短 |
| tick | 支持 | 仅实时快照 |
| 动态前复权 | 支持 | 不支持按历史日期锚定 |
| 稳定性 | 商业服务 | 依赖公开网页，可能变更 |

## 故障排查

- **`ImportError: 未安装 akshare`**：执行 `pip install bullet-trade[akshare]`。
- **返回空表**：确认代码是否为当前可交易标的、日期区间是否存在数据；分钟线请缩短区间。
- **接口报错或超时**：AKShare 依赖公开网页，稍后重试或切换数据源。
- **证券列表不含退市标的**：这是 AKShare 的固有限制，不是 Provider 配置问题。
