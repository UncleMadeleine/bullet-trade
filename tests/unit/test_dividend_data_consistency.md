# 分红数据一致性测试文档

## 测试目的

本测试套件用于验证不同数据源（JQData、MiniQMT、Tushare）返回的分红事件数据格式与数值的一致性。

## 为什么需要这个测试？

在之前的实现中，MiniQMT 数据源的 `get_split_dividend` 方法存在以下问题：
1. 错误地将 `per_base` 从 10 归一化为 1
2. 错误地将 `bonus_pre_tax` 除以 10
3. 没有正确区分股票和基金的分红口径

这些问题导致回测中的现金分红金额计算错误（少了10倍），但现有测试没有发现，因为：
- `test_exec_and_dividends_reference.py` 只测试了交易撮合逻辑
- 没有直接对比不同 provider 返回的原始分红数据

## 测试用例

### 黄金标准数据

基于聚宽官方数据，定义了以下分红事件作为黄金标准：

| 证券代码 | 分红日期 | per_base | bonus_pre_tax | 说明 |
|---------|----------|----------|---------------|------|
| 601318.XSHG | 2024-07-26 | 10 | 15.0000 | 每10股派15元 |
| 601318.XSHG | 2024-10-18 | 10 | 9.3000 | 每10股派9.3元 |
| 511880.XSHG | 2024-12-31 | 1 | 1.5521 | 每1份派1.5521元 |

### 测试场景

#### 1. `test_golden_dividends_format` (单元测试)
- 验证黄金标准数据本身的格式正确性
- 不需要网络连接
- 快速验证测试框架本身

#### 2. `test_provider_dividends_match_golden` (网络测试)
- 参数化测试：`jqdata`, `miniqmt`, `tushare`
- 验证每个 provider 返回的数据与黄金标准一致
- 检查字段：`date`, `per_base`, `bonus_pre_tax`, `security_type`, `scale_factor`

#### 3. `test_cross_provider_consistency` (网络测试)
- 交叉验证所有可用 provider 的数据一致性
- 确保不同数据源返回相同的分红数据
- 自动检测可用的 provider（至少需要2个）

#### 4. `test_dividend_cash_calculation` (单元测试)
- 验证分红现金计算公式的正确性
- 测试场景：
  - 601318.XSHG：1200股，税率20%，应入账1440元
  - 511880.XSHG：400份，免税，应入账620.84元

## 运行测试

### 前置条件

1. **环境变量配置**（至少配置一个数据源）：
   ```bash
   # JQData
   JQDATA_USERNAME=your_username
   JQDATA_PASSWORD=your_password
   
   # MiniQMT
   QMT_DATA_PATH=C:/path/to/qmt/data
   
   # Tushare
   TUSHARE_TOKEN=your_token
   ```

2. **安装依赖**：
   ```bash
   pip install -e ".[dev]"
   pip install jqdatasdk  # 如果测试 jqdata
   pip install xtquant    # 如果测试 miniqmt
   pip install tushare    # 如果测试 tushare
   ```

### 运行命令

```bash
# 只运行单元测试（不需要网络，快速验证）
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m unit -v

# 运行网络测试 - 默认测试 jqdata
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network -v

# 运行网络测试 - 测试特定 provider
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=miniqmt -v

# 运行网络测试 - 测试多个 provider（推荐）
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=jqdata,miniqmt,tushare -v

# 运行交叉一致性测试（会自动检测所有可用 provider）
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py::test_cross_provider_consistency -m requires_network -v -s

# 运行所有测试（单元测试 + 网络测试）
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=jqdata,miniqmt,tushare -v
```

**注意**：`--live-providers` 参数由 `conftest.py` 定义，用于指定要测试的数据源。如果不指定，默认只测试 `jqdata`。

### VS Code 调试配置

可以添加以下配置到 `.vscode/launch.json`：

```json
{
    "name": "Pytest: 分红数据一致性测试（仅单元测试）",
    "type": "python",
    "request": "launch",
    "module": "pytest",
    "args": [
        "bullet-trade/tests/unit/test_dividend_data_consistency.py",
        "-m", "unit",
        "-v", "-s"
    ],
    "console": "integratedTerminal"
},
{
    "name": "Pytest: 分红数据一致性测试（所有 provider）",
    "type": "python",
    "request": "launch",
    "module": "pytest",
    "args": [
        "bullet-trade/tests/unit/test_dividend_data_consistency.py",
        "-m", "requires_network",
        "--live-providers=jqdata,miniqmt,tushare",
        "-v", "-s"
    ],
    "console": "integratedTerminal"
}
```

## 预期结果

所有测试通过后，应该看到：

```
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_golden_dividends_format PASSED
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[jqdata] PASSED
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[miniqmt] PASSED
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[tushare] PASSED
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_cross_provider_consistency PASSED
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_dividend_cash_calculation PASSED
```

## 失败案例分析

### 示例1：per_base 不匹配
```
AssertionError: miniqmt 601318.XSHG 第1个分红事件 (2024-07-26) per_base 不匹配: 期望 10, 实际 1
```
**原因**：MiniQMTProvider 错误地将 `per_base` 归一化为 1

### 示例2：bonus_pre_tax 不匹配
```
AssertionError: miniqmt 601318.XSHG 第1个分红事件 (2024-07-26) bonus_pre_tax 不匹配: 期望 15.0, 实际 1.5
```
**原因**：MiniQMTProvider 错误地将 `bonus_pre_tax` 除以 10

## 数据格式规范

### 股票分红
```python
{
    "security": "601318.XSHG",
    "date": datetime.date(2024, 7, 26),
    "security_type": "stock",
    "per_base": 10,              # 每10股
    "bonus_pre_tax": 15.0,       # 派15元（税前）
    "scale_factor": 1.0,         # 无送转股
}
```

### 基金分红
```python
{
    "security": "511880.XSHG",
    "date": datetime.date(2024, 12, 31),
    "security_type": "fund",
    "per_base": 1,               # 每1份
    "bonus_pre_tax": 1.5521,     # 派1.5521元（税前）
    "scale_factor": 1.0,         # 无拆分
}
```

### 现金计算公式

```python
# 股票（有税）
cash_in = (持仓数量 / per_base) × bonus_pre_tax × (1 - 税率)

# 基金（免税）
cash_in = (持仓数量 / per_base) × bonus_pre_tax
```

## 维护建议

1. **添加新分红事件**：在 `GOLDEN_DIVIDENDS` 中添加新的测试数据
2. **支持新数据源**：在参数化测试中添加新的 provider 名称
3. **更新黄金标准**：如果聚宽数据有调整，及时更新黄金标准数据
4. **定期回归**：每次修改 provider 代码后，必须运行此测试套件

## 相关文件

- 实现文件：
  - `bullet_trade/data/providers/jqdata.py`
  - `bullet_trade/data/providers/miniqmt.py`
  - `bullet_trade/data/providers/tushare.py`
- 测试文件：
  - `tests/unit/test_exec_and_dividends_reference.py` (回测集成测试)
  - `tests/unit/test_dividend_data_consistency.py` (本测试套件)
