# 配置总览（回测/实盘/远程）

统一列出常用环境变量，避免在多页面重复。按照场景分组，可结合 `.env` 模板使用。

> 若需显式指定 `.env` 文件，可设置 `BT_ENV_FILE` / `BULLET_TRADE_ENV_FILE` / `ENV_FILE`，优先级高于自动向上查找。

## 通用
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `BT_ENV_FILE`/`BULLET_TRADE_ENV_FILE`/`ENV_FILE` | 否 | `./.env.live` | 指定要加载的 `.env` 路径，覆盖默认的向上查找逻辑 |
| `DEFAULT_DATA_PROVIDER` | 否 | `jqdata` | 默认行情源，回测/实盘共用（`jqdata`/`tushare`/`mysquant`/`qmt`） |
| `DEFAULT_BROKER` | 否 | `qmt` | 默认券商/交易通道（`simulator`/`qmt`/`qmt-remote`） |
| `DATA_CACHE_DIR` | 否 | `~/.bullet-trade/cache` | 行情缓存根目录，子目录按数据源名自动创建；留空禁用缓存 |
| `LOG_DIR` | 否 | `logs` | 日志目录 |
| `LOG_LEVEL` | 否 | `INFO` | 控制台日志级别（`DEBUG`/`INFO`/`WARNING`/`ERROR`） |
| `LOG_FILE_LEVEL` | 否 | 跟随 `LOG_LEVEL` | 文件日志级别，未设置则与 `LOG_LEVEL` 相同 |
| `RUNTIME_DIR` | 否 | `runtime` | 运行态/持久化目录（含 g.pkl、live_state.json） |

## 回测
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `DEFAULT_DATA_PROVIDER` | 是 | `jqdata` | 回测行情源 |
| `JQDATA_USERNAME`/`JQDATA_PASSWORD` | 视数据源 | `your_user`/`your_pwd` | 聚宽数据账号 |
| `JQDATA_SERVER`/`JQDATA_PORT` | 否 | `srv`/`8087` | 聚宽网关的地址/端口，不填则使用官方默认 |
| `TUSHARE_TOKEN` | 选 | `your_token` | 需 `tushare` 时配置 |
| `TUSHARE_CUSTOM_URL` | 否 | `http://127.0.0.1:port` | Tushare 自定义接入点 |
| `MYSQUANT_TOKEN` | 选 | `your_token` | 掘金量化 token，需在掘金平台申请 |
| `MYSQUANT_SERVER` | 否 | `localhost` | 自定义掘金终端地址（如本地运行终端） |
| `MYSQUANT_PORT` | 否 | `7070` | 自定义掘金终端端口 |
| `MINIQMT_MARKET` | 否 | `SH` | MiniQMT 行情源的市场代码（交易日/数据过滤），默认上交所 |

## 本地实盘（QMT/模拟）
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `DEFAULT_BROKER` | 是 | `qmt` 或 `simulator` | 交易通道 |
| `QMT_DATA_PATH` | 是 | `C:\国金QMT交易端\userdata_mini` | xtquant 数据目录 |
| `QMT_ACCOUNT_ID` | 是 | `123456` | QMT 账户 |
| `QMT_ACCOUNT_TYPE` | 否 | `stock` | 账户类型 |
| `MINIQMT_AUTO_DOWNLOAD` | 否 | `true` | 自动下载 MiniQMT |
| `QMT_SESSION_ID` | 否 | `0` | 会话 ID，可选 |
| `QMT_AUTO_SUBSCRIBE` | 否 | `true` | 连接 QMT 时是否自动订阅账户 |
| `SIMULATOR_INITIAL_CASH` | 否 | `1000000` | 模拟器初始资金（`simulator` 券商） |
| `MINIQMT_MARKET` | 否 | `SH` | 本地 MiniQMT 行情的市场代码 |

## 下单手数规则（security_overrides.json）
下单的最小手数与步进规则通过 `bullet_trade/config/security_overrides.json` 的 `lot_rules` 配置统一管理：
- `default`：默认规则（例如 A 股 100 股/100 股步进）
- `by_market`：按市场覆盖（北交所 `BJ`，兼容 `.BJ/.BSE`）
- `by_prefix`：按代码前缀覆盖（如科创板 `68`、可转债 `110/113/118/123/127/128`）
- `by_code`：单标覆盖

规则匹配时兼容聚宽后缀（`.XSHG/.XSHE`）与 QMT/Tushare 后缀（`.SH/.SZ`、`.BJ/.BSE`）。

## 风控（实盘）
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `MAX_ORDER_VALUE` | 否 | `100000` | 单笔订单金额上限，超出直接拒单。 |
| `MAX_DAILY_TRADE_VALUE` | 否 | `500000` | 单日累计成交金额上限，超出直接拒单。 |
| `MAX_DAILY_TRADES` | 否 | `100` | 单日最大交易笔数，超出直接拒单。 |
| `MAX_DAILY_CANCELS` | 否 | `100` | 单日最大撤单次数，超出直接拒绝撤单。 |
| `MIN_CANCEL_INTERVAL_SECONDS` | 否 | `0` | 两次撤单之间的最小间隔秒数，用于拦截撤单风暴。 |
| `MAX_CANCEL_PER_ORDER` | 否 | `3` | 单笔订单允许的最大撤单尝试次数。 |
| `MAX_STOCK_COUNT` | 否 | `20` | 最大持仓标的数（仅买入检查）。 |
| `MAX_POSITION_RATIO` | 否 | `20` | 单标下单金额占总资产上限，需要在风控检查时提供账户总资产才会生效。 |
| `STOP_LOSS_RATIO` | 否 | `5` | 止损阈值，供 `check_stop_loss` 辅助判断，需策略自行下撤单。 |
| `RISK_CHECK_ENABLED` | 否 | `false` | 后台风控巡检开关，间隔由 `RISK_CHECK_INTERVAL` 控制（默认 `300` 秒）。 |
| `RISK_CHECK_INTERVAL` | 否 | `300` | 风控后台巡检间隔（秒），仅 `RISK_CHECK_ENABLED=true` 时生效。 |

## 远程实盘（qmt-remote）
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `DEFAULT_BROKER` | 是 | `qmt-remote` | 远程通道 |
| `QMT_SERVER_HOST`/`QMT_SERVER_PORT` | 是 | `10.0.0.8`/`58620` | 远程服务地址 |
| `QMT_SERVER_TOKEN` | 是 | `secret` | 访问令牌 |
| `QMT_SERVER_ACCOUNT_KEY` | 否 | `main` | 多账户时指定 |
| `QMT_SERVER_SUB_ACCOUNT` | 否 | `demo@main` | 远程子账户标识，用于账户路由 |
| `QMT_SERVER_SUB_ACCOUNTS` | 否 | `demo@main:limit=50000` | server 侧子账户映射与单笔额度限制。 |
| `QMT_SERVER_ORDER_RISK_ENABLED` | 否 | `false` | 对 `broker.place_order` 与 `broker.cancel_order` 开启服务端风控，复用 `MAX_*` 与撤单限频参数。 |
| `QMT_SERVER_IDEMPOTENCY_TTL_SECONDS` | 否 | `300` | `broker.place_order` 幂等缓存窗口，避免链路重试导致重复下单。 |
| `QMT_SERVER_TLS_CERT` | 否 | `/path/to/ca.pem` | 启用 TLS 校验时的证书路径 |

## 聚宽模拟盘接入远程实盘
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `BT_REMOTE_HOST`/`BT_REMOTE_PORT` | 是 | `10.0.0.8`/`58620` | 远程 QMT server |
| `BT_REMOTE_TOKEN` | 是 | `secret` | 访问令牌 |
| `ACCOUNT_KEY`/`SUB_ACCOUNT` | 视账户 | `main`/`子账户` | 选填，匹配远程账户 |

## 实盘运行参数（LiveEngine）
| 变量 | 必填 | 示例/默认 | 作用 |
| --- | --- | --- | --- |
| `ORDER_MAX_VOLUME` | 否 | `1000000` | 单笔委托最大股数，超出自动拆单 |
| `TRADE_MAX_WAIT_TIME` | 否 | `16` | 同步下单/撤单等待秒数（<=0 走异步立即返回） |
| `EVENT_TIME_OUT` | 否 | `60` | 调度事件超时时间，延迟超过则丢弃当次事件 |
| `STRATEGY_NAME` | 否 | `demo-strategy` | 实盘订单备注中的策略标识，便于多策略并行排查；未设置时使用策略文件名 |
| `SCHEDULER_MARKET_PERIODS` | 否 | `09:30-11:30,13:00-15:00` | 自定义交易时段（期货/夜盘调试） |
| `ACCOUNT_SYNC_ENABLED`/`ACCOUNT_SYNC_INTERVAL` | 否 | `true`/`60` | 账户快照后台同步开关与间隔（秒） |
| `ORDER_SYNC_ENABLED`/`ORDER_SYNC_INTERVAL` | 否 | `true`/`10` | 订单状态轮询开关与间隔（秒） |
| `G_AUTOSAVE_ENABLED`/`G_AUTOSAVE_INTERVAL` | 否 | `true`/`60` | `g` 状态自动保存开关与间隔（秒） |
| `TICK_SUBSCRIPTION_LIMIT` | 否 | `100` | Tick 订阅标的数量上限 |
| `TICK_SYNC_ENABLED`/`TICK_SYNC_INTERVAL` | 否 | `true`/`2` | 无推送时的 Tick 轮询开关与间隔（秒） |
| `CALENDAR_SKIP_WEEKEND`/`CALENDAR_RETRY_MINUTES` | 否 | `true`/`1` | 非交易日检测：周末是否跳过、下一次检查间隔（分钟） |
| `BROKER_HEARTBEAT_INTERVAL` | 否 | `30` | 券商心跳后台任务间隔（秒，<=0 关闭） |
| `PORTFOLIO_REFRESH_THROTTLE_MS` | 否 | `200` | 访问实时持仓/资金前的最小刷新间隔（毫秒），防止高频刷接口 |
| `MARKET_BUY_PRICE_PERCENT`/`MARKET_SELL_PRICE_PERCENT` | 否 | `0.015`/`-0.015` | 市价单保护价偏移比例（正=买高、负=卖低，默认 ±1.5%） |

> 备注：实盘下单会生成 `bt:<strategy>:<shortid>` 格式的订单备注（仅 ASCII，<=24 字符），其中 `<strategy>` 优先使用 `STRATEGY_NAME`，未设置则取策略文件名短名。

> 提示：敏感信息不要入库，按需覆盖到本地 `.env`。***
