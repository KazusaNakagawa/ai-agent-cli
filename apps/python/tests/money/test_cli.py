import json

import pytest

from src.money.cli import main


def _run(args, store_path, rules_path=None):
    argv = ["--store", str(store_path)]
    if rules_path is not None:
        argv += ["--rules", str(rules_path)]
    main(argv + args)


class TestImportCommand:
    def test_reports_the_account_and_the_check_it_ran(
        self, rakuten_csv, manual_csv, store_path, capsys
    ):
        _run(["import", str(rakuten_csv), str(manual_csv)], store_path)
        out = capsys.readouterr().out
        assert "balance chain: verified" in out
        # The derived account is printed so a mistyped filename is visible
        # instead of quietly creating a second account.
        assert "口座 mufg" in out
        assert "新規 9 件" in out

    def test_dry_run_says_it_did_not_write(self, rakuten_csv, store_path, capsys):
        _run(["import", "--dry-run", str(rakuten_csv)], store_path)
        assert "--dry-run" in capsys.readouterr().out
        assert not store_path.exists()

    def test_a_missing_path_exits_with_a_readable_message(self, tmp_path, store_path):
        with pytest.raises(SystemExit) as exit_info:
            _run(["import", str(tmp_path / "nope.csv")], store_path)
        assert "no such file or directory" in str(exit_info.value)


class TestReportCommand:
    def test_defaults_to_the_most_recent_month(self, rakuten_csv, manual_csv, store_path, capsys):
        _run(["import", str(rakuten_csv), str(manual_csv)], store_path)
        capsys.readouterr()
        _run(["report", "--stdout"], store_path)
        assert "家計サマリー 2026-02" in capsys.readouterr().out

    def test_a_named_month_renders_its_own_summary(self, rakuten_csv, store_path, capsys):
        _run(["import", str(rakuten_csv)], store_path)
        capsys.readouterr()
        _run(["report", "--month", "2026-01", "--stdout"], store_path)
        assert "家計サマリー 2026-01" in capsys.readouterr().out

    def test_a_range_renders_one_row_per_month(self, rakuten_csv, store_path, capsys):
        _run(["import", str(rakuten_csv)], store_path)
        capsys.readouterr()
        _run(["report", "--range", "2026-01:2026-02", "--stdout"], store_path)
        out = capsys.readouterr().out
        assert "平均月支出" in out and "2026-01" in out and "2026-02" in out

    def test_a_month_with_no_data_says_what_is_available(self, rakuten_csv, store_path):
        _run(["import", str(rakuten_csv)], store_path)
        with pytest.raises(SystemExit) as exit_info:
            _run(["report", "--month", "2030-01", "--stdout"], store_path)
        assert "2026-01" in str(exit_info.value)

    def test_an_unpadded_month_is_a_usage_error(self, rakuten_csv, store_path):
        # Months are compared as text, so "2026-1" would sort outside every
        # real month and report missing data instead of a typo.
        _run(["import", str(rakuten_csv)], store_path)
        with pytest.raises(SystemExit) as exit_info:
            _run(["report", "--month", "2026-1", "--stdout"], store_path)
        assert "YYYY-MM" in str(exit_info.value)

    def test_a_range_endpoint_that_is_not_a_month_is_refused(self, rakuten_csv, store_path):
        _run(["import", str(rakuten_csv)], store_path)
        with pytest.raises(SystemExit) as exit_info:
            _run(["report", "--range", "2026-1:2026-2", "--stdout"], store_path)
        assert "YYYY-MM" in str(exit_info.value)

    def test_a_backwards_range_says_so(self, rakuten_csv, store_path):
        _run(["import", str(rakuten_csv)], store_path)
        with pytest.raises(SystemExit) as exit_info:
            _run(["report", "--range", "2026-02:2026-01", "--stdout"], store_path)
        assert "開始月が終了月より後" in str(exit_info.value)

    def test_reporting_before_importing_says_so(self, store_path):
        with pytest.raises(SystemExit) as exit_info:
            _run(["report", "--stdout"], store_path)
        assert "import" in str(exit_info.value)


class TestRulesTakeEffectWithoutReimporting:
    def test_a_new_rule_shows_up_in_the_next_report(
        self, rakuten_csv, store_path, tmp_path, capsys
    ):
        # Editing rules and re-running the report is the loop a person actually
        # works in. Classifications are re-derived on read so that loop works
        # without importing the statements again.
        rules_path = tmp_path / "money_rules.json"
        rules_path.write_text("{}", encoding="utf-8")
        _run(["import", str(rakuten_csv)], store_path, rules_path)
        capsys.readouterr()

        rules_path.write_text(
            json.dumps(
                {"categories": [{"pattern": "ショウケンガイシャ", "category": "investing", "label": "投資"}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _run(["report", "--month", "2026-02", "--stdout"], store_path, rules_path)
        assert "投資" in capsys.readouterr().out


class TestReviewCommand:
    def test_lists_coverage_unclassified_and_unpaired(self, rakuten_csv, store_path, capsys):
        _run(["import", str(rakuten_csv)], store_path)
        capsys.readouterr()
        _run(["review"], store_path)
        out = capsys.readouterr().out
        assert "カバー期間" in out
        assert "2026-01-05 〜 2026-02-10" in out
        assert "未分類" in out
        assert "振替候補" in out
