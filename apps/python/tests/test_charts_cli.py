from pathlib import Path

from src.charts import __main__ as cli


def test_price_passes_explicit_args(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_generate(tickers, output_dir, period):
        captured["tickers"] = tickers
        captured["output_dir"] = output_dir
        captured["period"] = period
        return output_dir / "price-comparison-20260629.png"

    monkeypatch.setattr(cli, "generate_price_comparison", fake_generate)

    rc = cli.main(
        ["price", "--tickers", "PLTR", "NVDA", "--output-dir", str(tmp_path), "--period", "1mo"]
    )

    assert rc == 0
    assert captured["tickers"] == ["PLTR", "NVDA"]
    assert captured["output_dir"] == tmp_path
    assert captured["period"] == "1mo"
    assert "saved:" in capsys.readouterr().out


def test_price_defaults_to_config_tickers(tmp_path, monkeypatch):
    captured = {}

    def fake_generate(tickers, output_dir, period):
        captured["tickers"] = tickers
        return Path("x.png")

    monkeypatch.setattr(cli, "generate_price_comparison", fake_generate)

    # Stub the lazily-imported config so the test stays config-file-independent.
    import types

    fake_config = types.SimpleNamespace(
        portfolio=types.SimpleNamespace(tickers=["AAA", "BBB"])
    )
    monkeypatch.setitem(
        __import__("sys").modules, "src.config", types.SimpleNamespace(CONFIG=fake_config)
    )

    rc = cli.main(["price", "--output-dir", str(tmp_path)])

    assert rc == 0
    assert captured["tickers"] == ["AAA", "BBB"]
