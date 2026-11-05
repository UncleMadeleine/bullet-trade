import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _build_args(strategy_file: Path, output_dir: Path, **overrides):
    args = {
        "strategy_file": str(strategy_file),
        "start": "2025-04-01",
        "end": "2025-12-30",
        "cash": 1000000,
        "frequency": "day",
        "benchmark": "000300.XSHG",
        "output": str(output_dir),
        "log": None,
        "generate_images": False,
        "generate_csv": True,
        "generate_html": True,
        "generate_logs": False,
        "auto_report": True,
        "report_format": "html",
        "report_template": None,
        "report_metrics": None,
        "report_title": None,
        "report_output": None,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


def _install_fake_backtest_modules(monkeypatch, captured):
    engine_module = ModuleType("bullet_trade.core.engine")
    analysis_module = ModuleType("bullet_trade.core.analysis")
    reporting_module = ModuleType("bullet_trade.reporting")

    def fake_create_backtest(**kwargs):
        captured["create_backtest_kwargs"] = kwargs
        return {"metrics": {"策略收益": 12.0, "策略年化收益": 8.0, "最大回撤": -3.0, "夏普比率": 1.5}}

    def fake_generate_report(results, output_dir, gen_images, gen_csv, gen_html):
        captured["generate_report_args"] = {
            "results": results,
            "output_dir": output_dir,
            "gen_images": gen_images,
            "gen_csv": gen_csv,
            "gen_html": gen_html,
        }

    def fake_generate_cli_report(**kwargs):
        captured["generate_cli_report_kwargs"] = kwargs
        return Path(kwargs["output_path"])

    class FakeReportGenerationError(Exception):
        pass

    engine_module.create_backtest = fake_create_backtest
    analysis_module.generate_report = fake_generate_report
    reporting_module.generate_cli_report = fake_generate_cli_report
    reporting_module.ReportGenerationError = FakeReportGenerationError

    monkeypatch.setitem(sys.modules, "bullet_trade.core.engine", engine_module)
    monkeypatch.setitem(sys.modules, "bullet_trade.core.analysis", analysis_module)
    monkeypatch.setitem(sys.modules, "bullet_trade.reporting", reporting_module)


def test_run_backtest_auto_report_uses_standard_report_by_default(tmp_path, monkeypatch):
    from bullet_trade.cli.backtest import run_backtest

    captured = {}
    _install_fake_backtest_modules(monkeypatch, captured)

    strategy_file = tmp_path / "backtest_v2.py"
    strategy_file.write_text("# test strategy\n", encoding="utf-8")
    output_dir = tmp_path / "backtest_results"
    args = _build_args(strategy_file, output_dir)

    exit_code = run_backtest(args)

    assert exit_code == 0
    assert captured["generate_report_args"]["output_dir"] == str(output_dir)
    assert captured["generate_cli_report_kwargs"]["input_dir"] == str(output_dir)
    assert captured["generate_cli_report_kwargs"]["output_path"] == str(
        output_dir / "standard_report.html"
    )


def test_run_backtest_auto_report_respects_custom_output(tmp_path, monkeypatch):
    from bullet_trade.cli.backtest import run_backtest

    captured = {}
    _install_fake_backtest_modules(monkeypatch, captured)

    strategy_file = tmp_path / "backtest_v2.py"
    strategy_file.write_text("# test strategy\n", encoding="utf-8")
    output_dir = tmp_path / "backtest_results"
    custom_output = tmp_path / "reports" / "custom-summary.html"
    args = _build_args(strategy_file, output_dir, report_output=str(custom_output))

    exit_code = run_backtest(args)

    assert exit_code == 0
    assert captured["generate_cli_report_kwargs"]["output_path"] == str(custom_output)


def test_create_parser_supports_report_output():
    from bullet_trade.cli.main import create_parser

    parser = create_parser()
    args = parser.parse_args(
        [
            "backtest",
            "strategy.py",
            "--start",
            "2025-04-01",
            "--end",
            "2025-12-30",
            "--report-output",
            "reports/summary.html",
        ]
    )

    assert args.report_output == "reports/summary.html"
