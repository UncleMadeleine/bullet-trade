# 掘金量化 (MyQuant) 数据源封装说明

`MysQuantProvider` 位于 `bullet_trade/data/providers/mysquant.py`，通过 `DEFAULT_DATA_PROVIDER=mysquant` 或 `set_data_provider('mysquant', token='xxx')` 激活。

## 安装与认证

- 依赖 `gm-sdk`（掘金量化 Python SDK），建议通过 `pip install bullet-trade[mysquant]` 一键安装。
- 认证方式：使用 `MYSQUANT_TOKEN` 环境变量或在 `set_data_provider` 中传入 `token` 参数。
- Provider 会在首次调用时自动调用 `gm.set_token()` 完成认证。
- 如需连接本地掘金终端（默认端口 7070），可设置 `MYSQUANT_SERVER` 和 `MYSQUANT_PORT` 环境变量。

## 代码格式

掘金使用 `EXCHANGE.CODE` 格式（例如 `SHSE.600000`、`SZSE.000001`）。Provider 内部会自动转换为聚宽格式（`600000.XSHG`）以保持与其他数据源的一致性。

## 价格获取

- 主要接口：`gm.history()`，支持频率：`tick`、`1d`、`60s`、`300s`、`900s`、`1800s`、`3600s`。
- BulletTrade 的频率映射：
  - `daily`/`1d` → `1d`
  - `minute`/`1m` → `60s`
  - `5m` → `300s`
  - `15m` → `900s`
  - `30m` → `1800s`
  - `60m` → `3600s`
- 复权方式：`ADJUST_PREV`（前复权）、`ADJUST_POST`（后复权）、`ADJUST_NONE`（不复权），对应 BulletTrade 的 `fq='pre'/'post'/'none'`。
- 多标的请求会拆分为单标的调用，并根据 `panel` 参数拼接结果（`panel=True` 为列 MultiIndex，`panel=False` 输出长表）。

## 交易日

- 使用 `gm.get_trading_calendar()` 获取交易日历，默认以上交所为准。

## 证券列表

- 通过 `gm.get_symbol_infos()` 查询标的基本信息。
- 支持类型：`stock`、`fund`、`etf`、`index`。
- 若传入 `date` 参数，会根据标的的上市/退市日期进行过滤。

## 指数成分股

- 使用 `gm.stk_get_index_constituents()` 查询指数成分股，返回 JQ 格式代码列表。

## 分红与拆分

- 使用 `gm.stk_get_dividend()` 获取分红数据。
- 事件标准化为：
  - `scale_factor = 1 + (stock_dividend_ratio + transfer_ratio) / 10`
  - `bonus_pre_tax` 为每股派息（现金红利）
  - `per_base = 10`
- 注意：掘金的分红数据可能因权限而异，若接口不可用则返回空列表。

## 实时行情

- `get_current_tick()` 调用 `gm.current()` 获取当前快照。
- `get_live_current()` 返回最小字段集：`last_price`、`high_limit`、`low_limit`、`paused`。
- 停牌判断依据：成交量是否为 0（掘金 tick 数据中的 `volume` 字段）。

## 使用提示

1. **终端依赖**：掘金 SDK 依赖本地或远程的掘金量化终端服务，请确保终端已启动并登录。
2. **Token 权限**：不同权限的 token 可访问的数据范围不同，请确保 token 具备所需数据的读取权限。
3. **缓存配置**：建议设置 `DATA_CACHE_DIR` 以缓存历史数据，减少网络请求。
4. **频率限制**：免费 token 可能有调用频率限制，实盘环境请使用付费 token。
5. **复权处理**：Provider 不包含复杂的复权因子引擎，若需精确的前复权（特别是 `pre_factor_ref_date` 指定日期），建议在策略端自行处理或使用 JQData 的引擎。

## 与 JQData 的差异

| 特性 | JQData | MysQuant |
|------|--------|----------|
| 数据源 | 聚宽云端 | 掘金量化终端 |
| 代码格式 | `600000.XSHG` | `SHSE.600000` |
| 认证 | 用户名/密码 | Token |
| 实时订阅 | 内置推送 | 需通过 `subscribe` 订阅（当前 Provider 使用 `current` 轮询式获取） |
| 复权因子 | 完整因子表 | 依赖 `history` 的 `adjust` 参数，无独立因子接口 |

## 快速开始

```python
import os
from bullet_trade import set_data_provider, get_price

# 方式1：环境变量
os.environ['DEFAULT_DATA_PROVIDER'] = 'mysquant'
os.environ['MYSQUANT_TOKEN'] = 'your_token_here'

# 方式2：代码设置
set_data_provider('mysquant', token='your_token_here')

# 获取行情
df = get_price('SHSE.600000', start_date='2024-01-01', end_date='2024-12-31', frequency='daily')
print(df.head())
```

## 故障排查

- **认证失败**：检查 token 是否正确，终端是否登录。
- **无数据返回**：确认标的代码格式、交易日期是否为交易日、token 权限是否足够。
- **连接超时**：检查 `MYSQUANT_SERVER`/`MYSQUANT_PORT` 是否指向正确的终端地址。
