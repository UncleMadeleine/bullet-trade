"""
测试 get_price 的 panel 参数行为

验证 jqdatasdk 的 get_price 返回格式是否与聚宽官方一致：
- panel=True: 返回 MultiIndex 宽表
- panel=False: 返回包含 time 和 code 列的长表

使用方法：
1. 配置聚宽官方服务器，运行测试，应该全部通过
2. 配置自己的服务器，运行测试，如果不通过会输出详细的错误信息

运行命令：
    pytest tests/unit/test_get_price_panel.py -v -s
"""
import pandas as pd
import pytest

# 测试参数
TEST_STOCKS = ["000001.XSHE", "000002.XSHE", "600000.XSHG"]
TEST_END_DATE = "2023-12-20"
TEST_COUNT = 3
TEST_FIELDS = ["close", "money"]

pytestmark = [pytest.mark.requires_network, pytest.mark.requires_jqdata]


def _format_columns(columns) -> str:
    """格式化列信息，方便调试"""
    if hasattr(columns, "tolist"):
        return str(columns.tolist())
    return str(list(columns))


def _format_dataframe_info(df: pd.DataFrame) -> str:
    """格式化 DataFrame 信息，方便调试"""
    lines = [
        f"  type: {type(df)}",
        f"  shape: {df.shape}",
        f"  columns: {_format_columns(df.columns)}",
        f"  columns.dtype: {type(df.columns)}",
        f"  index.dtype: {type(df.index)}",
    ]
    if hasattr(df.columns, "names"):
        lines.append(f"  columns.names: {df.columns.names}")
    if hasattr(df.columns, "nlevels"):
        lines.append(f"  columns.nlevels: {df.columns.nlevels}")
    lines.append(f"  head(5):\n{df.head(5).to_string()}")
    return "\n".join(lines)


@pytest.fixture(scope="module")
def jq_auth():
    """
    认证 jqdatasdk

    从当前目录的 .env 文件读取配置，支持以下变量：
    - JQDATA_USERNAME: 聚宽用户名（必需）
    - JQDATA_PASSWORD: 聚宽密码（必需）
    - JQDATA_HOST: 自定义服务器地址（可选，不填则使用聚宽官方）
    - JQDATA_PORT: 自定义服务器端口（可选）
    """
    import os
    from pathlib import Path

    # 查找 .env 文件的可能位置
    possible_paths = [
        Path(".env"),  # 当前目录
        # Path('bullet-trade/.env'),              # bullet-trade 子目录
        # Path(__file__).parent.parent.parent / '.env',  # tests 的上级目录
    ]

    # 手动读取 .env 文件
    env_vars = {}
    env_file_found = None

    for env_path in possible_paths:
        if env_path.exists():
            env_file_found = env_path
            print(f"\n从 {env_path.absolute()} 读取配置")
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        env_vars[key] = value
            break

    if not env_file_found:
        # 尝试从环境变量获取
        print("\n未找到 .env 文件，尝试从环境变量获取")
        env_vars = {
            "JQDATA_USERNAME": os.getenv("JQDATA_USERNAME"),
            "JQDATA_PASSWORD": os.getenv("JQDATA_PASSWORD"),
            "JQDATA_SERVER": os.getenv("JQDATA_SERVER"),
            "JQDATA_PORT": os.getenv("JQDATA_PORT"),
        }

    username = env_vars.get("JQDATA_USERNAME")
    password = env_vars.get("JQDATA_PASSWORD")
    host = env_vars.get("JQDATA_SERVER")
    port = env_vars.get("JQDATA_PORT")

    if not username or not password:
        pytest.skip(
            "缺少 JQDATA_USERNAME 或 JQDATA_PASSWORD\n"
            "请在 .env 文件中配置：\n"
            "  JQDATA_USERNAME=你的用户名\n"
            "  JQDATA_PASSWORD=你的密码\n"
            "  JQDATA_HOST=服务器地址（可选）\n"
            "  JQDATA_PORT=服务器端口（可选）"
        )

    import jqdatasdk as jq

    # 如果有自定义 host/port，使用它们
    if host and port:
        jq.auth(username, password, host=host, port=int(port))
        print(f"使用自定义服务器: {host}:{port}")
    else:
        jq.auth(username, password)
        print("使用聚宽官方服务器")

    return jq


class TestGetPricePanelTrue:
    """
    测试 panel=True 时的返回格式

    注意：聚宽官方在新版本中可能统一返回长表格式（因为 pandas.Panel 已在 0.25.0 移除）
    因此这里接受两种格式：
    1. MultiIndex 宽表（旧版行为）
    2. 长表格式（新版行为，与 panel=False 相同）
    """

    def test_panel_true_returns_valid_format(self, jq_auth):
        """
        panel=True 时，返回有效的 DataFrame

        可接受的格式：
        1. MultiIndex 宽表：列是 MultiIndex(field, code)，行是日期
        2. 长表：列是 ['time', 'code'] + fields，行是每个股票每个时间点
        """
        jq = jq_auth

        # 调用参数
        params = {
            "security": TEST_STOCKS,
            "end_date": TEST_END_DATE,
            "count": TEST_COUNT,
            "fields": TEST_FIELDS,
            "panel": True,
        }

        print(f"\n调用参数: {params}")

        df = jq.get_price(**params)

        print(f"\n返回结果:\n{_format_dataframe_info(df)}")

        # 验证返回类型
        assert isinstance(df, pd.DataFrame), (
            f"panel=True 时应返回 DataFrame\n" f"传入参数: {params}\n" f"实际返回类型: {type(df)}"
        )

        # 检查是哪种格式
        is_multiindex = isinstance(df.columns, pd.MultiIndex)
        is_long_format = "time" in df.columns and "code" in df.columns

        if is_multiindex:
            print("\n检测到 MultiIndex 宽表格式（旧版行为）")
            # 验证 MultiIndex 有两层
            assert df.columns.nlevels == 2, (
                f"panel=True 时列的 MultiIndex 应有 2 层\n" f"实际层数: {df.columns.nlevels}"
            )
            # 验证行数等于时间点数
            assert len(df) == TEST_COUNT, (
                f"panel=True 宽表格式时，行数应等于 count\n" f"期望行数: {TEST_COUNT}\n" f"实际行数: {len(df)}"
            )
        elif is_long_format:
            print("\n检测到长表格式（新版行为，与聚宽官方一致）")
            # 验证包含请求的字段
            for field in TEST_FIELDS:
                assert field in df.columns, (
                    f"长表格式应包含字段 '{field}'\n" f"实际列: {_format_columns(df.columns)}"
                )
            # 验证行数 = 股票数 × 时间点数
            expected_rows = len(TEST_STOCKS) * TEST_COUNT
            assert len(df) == expected_rows, (
                f"长表格式时，行数应等于 股票数 × 时间点数\n" f"期望行数: {expected_rows}\n" f"实际行数: {len(df)}"
            )
        else:
            pytest.fail(
                f"panel=True 时返回格式不符合预期\n"
                f"传入参数: {params}\n"
                f"实际列: {_format_columns(df.columns)}\n"
                f"\n期望格式（二选一）：\n"
                f"  1. MultiIndex 宽表：列是 [('close', 'code1'), ('close', 'code2'), ...]\n"
                f"  2. 长表：列是 ['time', 'code', 'close', 'money']"
            )

        print("\n✓ panel=True 测试通过")


class TestGetPricePanelFalse:
    """测试 panel=False 时的返回格式（长表）"""

    def test_panel_false_returns_long_format(self, jq_auth):
        """
        panel=False 时，应返回包含 time 和 code 列的长表

        预期格式：
        - 列：['time', 'code'] + fields
        - 行数：等于 时间点数 × 股票数
        - 每行代表一个股票的一个时间点的数据
        """
        jq = jq_auth

        # 调用参数
        params = {
            "security": TEST_STOCKS,
            "end_date": TEST_END_DATE,
            "count": TEST_COUNT,
            "fields": TEST_FIELDS,
            "panel": False,
        }

        print(f"\n调用参数: {params}")

        df = jq.get_price(**params)

        print(f"\n返回结果:\n{_format_dataframe_info(df)}")

        # 验证返回类型
        assert isinstance(df, pd.DataFrame), (
            f"panel=False 时应返回 DataFrame\n" f"传入参数: {params}\n" f"实际返回类型: {type(df)}"
        )

        # 验证列不是 MultiIndex（应该是普通列）
        is_multiindex = isinstance(df.columns, pd.MultiIndex)
        if is_multiindex:
            print("\n✗ 错误：panel=False 时列不应为 MultiIndex")
            print(f"传入参数: {params}")
            print(f"实际列类型: {type(df.columns)}")
            print(f"实际列内容: {_format_columns(df.columns)}")
            print("\n期望格式：")
            print("  columns: ['time', 'code', 'close', 'money']")
            print("  每行代表一个股票的一个时间点的数据")
            print(
                f"  行数 = 股票数({len(TEST_STOCKS)}) × 时间点数({TEST_COUNT}) = {len(TEST_STOCKS) * TEST_COUNT}"
            )
            pytest.fail(
                "panel=False 时列不应为 MultiIndex，应该是普通列 ['time', 'code', ...]\n"
                "请修改服务端，让 panel=False 时返回长表格式"
            )

        # 验证必须包含 'time' 列
        assert "time" in df.columns, (
            f"panel=False 时必须包含 'time' 列\n"
            f"传入参数: {params}\n"
            f"实际列: {_format_columns(df.columns)}\n"
            f"\n期望格式：\n"
            f"  columns: ['time', 'code', 'close', 'money']"
        )

        # 验证必须包含 'code' 列
        assert "code" in df.columns, (
            f"panel=False 时必须包含 'code' 列\n"
            f"传入参数: {params}\n"
            f"实际列: {_format_columns(df.columns)}\n"
            f"\n期望格式：\n"
            f"  columns: ['time', 'code', 'close', 'money']"
        )

        # 验证包含请求的字段
        for field in TEST_FIELDS:
            assert field in df.columns, (
                f"panel=False 时应包含请求的字段 '{field}'\n"
                f"传入参数: {params}\n"
                f"实际列: {_format_columns(df.columns)}"
            )

        # 验证行数 = 股票数 × 时间点数
        expected_rows = len(TEST_STOCKS) * TEST_COUNT
        assert len(df) == expected_rows, (
            f"panel=False 时行数应等于 股票数 × 时间点数\n"
            f"传入参数: {params}\n"
            f"期望行数: {len(TEST_STOCKS)} × {TEST_COUNT} = {expected_rows}\n"
            f"实际行数: {len(df)}"
        )

        # 验证 code 列包含所有股票
        codes_in_df = set(df["code"].unique())
        expected_stocks = set(TEST_STOCKS)
        assert codes_in_df == expected_stocks, (
            f"panel=False 时 code 列应包含所有请求的股票\n"
            f"传入参数: {params}\n"
            f"期望股票: {expected_stocks}\n"
            f"实际股票: {codes_in_df}"
        )

        # 验证每只股票有 count 条记录
        for stock in TEST_STOCKS:
            stock_rows = len(df[df["code"] == stock])
            assert stock_rows == TEST_COUNT, (
                f"panel=False 时每只股票应有 {TEST_COUNT} 条记录\n"
                f"传入参数: {params}\n"
                f"股票 {stock} 实际记录数: {stock_rows}"
            )

        print("\n✓ panel=False 测试通过")


class TestGetPriceSingleStock:
    """测试单只股票时的返回格式"""

    def test_single_stock_panel_true(self, jq_auth):
        """单只股票，panel=True"""
        jq = jq_auth

        params = {
            "security": "000001.XSHE",
            "end_date": TEST_END_DATE,
            "count": TEST_COUNT,
            "fields": TEST_FIELDS,
            "panel": True,
        }

        print(f"\n调用参数: {params}")

        df = jq.get_price(**params)

        print(f"\n返回结果:\n{_format_dataframe_info(df)}")

        assert isinstance(df, pd.DataFrame), f"应返回 DataFrame，实际: {type(df)}"
        assert len(df) == TEST_COUNT, f"行数应为 {TEST_COUNT}，实际: {len(df)}"

        # 单只股票时，列应该直接是字段名（不是 MultiIndex）
        for field in TEST_FIELDS:
            assert field in df.columns, f"应包含字段 '{field}'，实际列: {_format_columns(df.columns)}"

        print("\n✓ 单只股票 panel=True 测试通过")

    def test_single_stock_panel_false(self, jq_auth):
        """单只股票，panel=False"""
        jq = jq_auth

        params = {
            "security": "000001.XSHE",
            "end_date": TEST_END_DATE,
            "count": TEST_COUNT,
            "fields": TEST_FIELDS,
            "panel": False,
        }

        print(f"\n调用参数: {params}")

        df = jq.get_price(**params)

        print(f"\n返回结果:\n{_format_dataframe_info(df)}")

        assert isinstance(df, pd.DataFrame), f"应返回 DataFrame，实际: {type(df)}"
        assert len(df) == TEST_COUNT, f"行数应为 {TEST_COUNT}，实际: {len(df)}"

        # 单只股票时，直接返回字段作为列即可
        for field in TEST_FIELDS:
            assert field in df.columns, f"应包含字段 '{field}'，实际列: {_format_columns(df.columns)}"

        print("\n✓ 单只股票 panel=False 测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
