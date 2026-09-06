import pytest

from src.money import report as report_mod
from src.money import store
from src.money.importer import import_paths
from src.money.models import MoneyError


class TestImport:
    def test_stores_every_row_from_both_accounts(self, rakuten_csv, manual_csv, store_path, rules):
        summary = import_paths(
            [rakuten_csv, manual_csv], store_path=store_path, rules=rules
        )
        assert summary.added == 9
        assert summary.stored == 9
        assert store_path.exists()

    def test_reimporting_the_same_file_changes_nothing(self, rakuten_csv, store_path, rules):
        import_paths([rakuten_csv], store_path=store_path, rules=rules)
        again = import_paths([rakuten_csv], store_path=store_path, rules=rules)
        assert (again.added, again.duplicates) == (0, 5)
        assert again.stored == 5

    def test_a_renamed_copy_is_still_a_duplicate(self, rakuten_csv, store_path, rules, tmp_path):
        # Statements get re-downloaded under a new name all the time; identity
        # has to come from the content, not the filename.
        import_paths([rakuten_csv], store_path=store_path, rules=rules)
        copy = tmp_path / "RB-torihikimeisai-20260823.csv"
        copy.write_bytes(rakuten_csv.read_bytes())
        again = import_paths([copy], store_path=store_path, rules=rules)
        assert (again.added, again.stored) == (0, 5)

    def test_dry_run_verifies_without_writing(self, rakuten_csv, store_path, rules):
        summary = import_paths(
            [rakuten_csv], store_path=store_path, rules=rules, dry_run=True
        )
        assert summary.added == 5
        assert not store_path.exists()

    def test_a_directory_is_expanded(self, rakuten_csv, manual_csv, store_path, rules):
        summary = import_paths([rakuten_csv.parent], store_path=store_path, rules=rules)
        assert {f.parser for f in summary.files} == {"rakuten_bank", "manual"}

    def test_a_directory_sweep_skips_formats_this_phase_cannot_read(
        self, rakuten_csv, store_path, rules
    ):
        # Card statements sit in the same folder waiting for a later phase.
        # One unreadable file must not block importing the bank statements.
        other = rakuten_csv.parent / "202608.csv"
        other.write_text("利用日,利用店名,利用金額\n2026/07/01,X,880\n", encoding="utf-8")
        summary = import_paths([rakuten_csv.parent], store_path=store_path, rules=rules)
        assert [p.name for p, _ in summary.skipped] == ["202608.csv"]
        assert summary.added == 5

    def test_naming_an_unreadable_file_is_still_an_error(self, store_path, rules, tmp_path):
        # Asking for one file by name and silently doing nothing would be worse
        # than failing, so the skip only applies to directory sweeps.
        other = tmp_path / "202608.csv"
        other.write_text("利用日,利用店名,利用金額\n2026/07/01,X,880\n", encoding="utf-8")
        with pytest.raises(MoneyError, match="no parser recognizes"):
            import_paths([other], store_path=store_path, rules=rules)

    def test_a_failing_file_leaves_the_store_untouched(self, rakuten_csv, store_path, rules, tmp_path):
        import_paths([rakuten_csv], store_path=store_path, rules=rules)
        before = store_path.read_text(encoding="utf-8")
        broken = tmp_path / "broken.csv"
        broken.write_bytes(
            (
                "取引日,入出金(円),取引後残高(円),入出金内容\r\n"
                "20260105,300000,1300000,ヤマダ\r\n"
                "20260127,-12000,999,ホケン\r\n"
            ).encode("cp932")
        )
        with pytest.raises(MoneyError):
            import_paths([broken], store_path=store_path, rules=rules)
        assert store_path.read_text(encoding="utf-8") == before

    def test_importing_the_second_account_turns_a_stored_row_into_a_transfer(
        self, rakuten_csv, manual_csv, store_path, rules
    ):
        # The other half of a transfer routinely arrives in a later import.
        # Pairing therefore runs over the whole store, not just the new rows.
        import_paths([rakuten_csv], store_path=store_path, rules=rules)
        first = {t.id: t for t in store.load(store_path)}
        incoming = next(t for t in first.values() if t.amount == 300000)
        assert incoming.transfer_peer is None

        import_paths([manual_csv], store_path=store_path, rules=rules)
        after = {t.id: t for t in store.load(store_path)}
        assert after[incoming.id].is_transfer is True
        assert after[incoming.id].transfer_peer is not None


class TestReport:
    @pytest.fixture
    def transactions(self, rakuten_csv, manual_csv, store_path, rules):
        import_paths([rakuten_csv, manual_csv], store_path=store_path, rules=rules)
        return store.load(store_path)

    def test_a_transfer_between_your_own_accounts_is_not_spending(self, transactions):
        # Both halves of the 300,000 move are excluded; counting either one
        # would flip the month's result.
        january = report_mod.summarize_month(transactions, "2026-01")
        assert january.income == 250500
        assert january.expense == 72000
        assert january.transfers_excluded == 2

    def test_savings_rate_uses_income_actually_received(self, transactions):
        january = report_mod.summarize_month(transactions, "2026-01")
        assert january.net == 178500
        assert january.savings_rate == pytest.approx(178500 / 250500)

    def test_a_month_with_no_income_has_no_savings_rate(self, transactions):
        # Dividing by zero income would print a nonsense percentage.
        february = report_mod.summarize_month(transactions, "2026-02")
        assert february.savings_rate is None

    def test_a_brokerage_transfer_is_excluded_from_spending(self, transactions):
        # Only one side of this exists in the data, so the rule is what keeps
        # it out — without it February would report a huge fake expense.
        february = report_mod.summarize_month(transactions, "2026-02")
        assert february.expense == 0
        assert february.transfers_excluded == 1

    def test_months_covered_is_sorted(self, transactions):
        assert report_mod.months_covered(transactions) == ["2026-01", "2026-02"]

    def test_rendered_month_reports_unclassified_rows(self, transactions, rules):
        text = report_mod.render_month(
            report_mod.summarize_month(transactions, "2026-01"), rules
        )
        assert "家計サマリー 2026-01" in text
        assert "未分類" in text

    def test_savings_rate_moves_in_points_not_percent(self, rules):
        # The difference between two rates is a point spread; printing it as a
        # percentage would read as though the rate itself had that value.
        previous = report_mod.MonthSummary(month="2026-01", income=100, expense=50)
        current = report_mod.MonthSummary(month="2026-02", income=100, expense=25)
        text = report_mod.render_month(current, rules, previous=previous)
        assert "| 貯蓄率 | 75.0% | +25.0pt |" in text

    def test_savings_rate_delta_is_blank_without_income(self, rules):
        previous = report_mod.MonthSummary(month="2026-01", income=100, expense=50)
        current = report_mod.MonthSummary(month="2026-02", income=0, expense=25)
        text = report_mod.render_month(current, rules, previous=previous)
        assert "| 貯蓄率 | — | — |" in text

    def test_category_rows_use_the_label_from_the_rules(self, transactions, rules):
        # A report is read by a person, so it shows 「利息」 rather than the
        # internal key `income_interest`.
        text = report_mod.render_month(
            report_mod.summarize_month(transactions, "2026-01"), rules
        )
        assert "| 利息 |" in text
        assert "income_interest" not in text

    def test_conflicting_labels_fall_back_to_the_category_key(self):
        # Two counterparties under one category with different labels: showing
        # the combined total under one of their names would read as though that
        # one counterparty cost all of it.
        from src.money.rules import CategoryRule, Rules, make_matcher

        rules = Rules(
            categories=[
                CategoryRule(make_matcher("A", where="t"), "insurance", label="ホケンA"),
                CategoryRule(make_matcher("B", where="t"), "insurance", label="ホケンB"),
            ]
        )
        assert report_mod.category_labels(rules) == {}

    def test_rendered_range_totals_every_month(self, transactions, rules):
        text = report_mod.render_range(transactions, ["2026-01", "2026-02"])
        assert "2026-01" in text and "2026-02" in text
        assert "平均月支出" in text
