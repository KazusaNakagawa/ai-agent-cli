import pytest

from src.money.models import MoneyError
from src.money.parsers import detect, parse_file, read_text


class TestRakutenBank:
    def test_reads_cp932_and_normalizes_the_date(self, rakuten_csv):
        result = parse_file(rakuten_csv)
        assert result.parser == "rakuten_bank"
        assert result.account == "rakuten_bank"
        assert result.transactions[0].date == "2026-01-05"

    def test_keeps_the_signed_amount_convention(self, rakuten_csv):
        amounts = [t.amount for t in parse_file(rakuten_csv).transactions]
        assert amounts == [300000, -12000, -40000, 500, -800000]

    def test_normalizes_the_description_while_keeping_the_original(self, rakuten_csv):
        insurance = parse_file(rakuten_csv).transactions[1]
        assert insurance.desc == "DF.ゼンホケン"
        assert insurance.desc_raw == "ＤＦ．セ゛ンホケン"

    def test_reports_the_balance_chain_as_verified(self, rakuten_csv):
        assert parse_file(rakuten_csv).checks == ["balance chain: verified (5 rows)"]

    def test_refuses_a_file_whose_balance_chain_breaks(self, tmp_path):
        # A dropped or mistyped row is invisible in the totals but shows up
        # immediately here, which is what makes a transcribed statement usable.
        text = (
            "取引日,入出金(円),取引後残高(円),入出金内容\r\n"
            "20260105,300000,1300000,ヤマダ\r\n"
            "20260127,-12000,1111111,ホケン\r\n"
        )
        path = tmp_path / "broken.csv"
        path.write_bytes(text.encode("cp932"))
        with pytest.raises(MoneyError, match="balance chain broken"):
            parse_file(path)


class TestManual:
    def test_collapses_two_columns_into_one_signed_amount(self, manual_csv):
        amounts = [t.amount for t in parse_file(manual_csv).transactions]
        assert amounts == [-300000, 250000, -10000, -10000]

    def test_takes_the_account_from_the_filename(self, manual_csv):
        result = parse_file(manual_csv)
        assert result.account == "mufg"
        assert all(t.account == "mufg" for t in result.transactions)

    def test_verifies_the_balance_chain_too(self, manual_csv):
        assert parse_file(manual_csv).checks == ["balance chain: verified (4 rows)"]

    def test_two_identical_rows_are_kept_apart(self, manual_csv):
        rows = parse_file(manual_csv).transactions
        assert rows[2].id != rows[3].id

    def test_rejects_a_row_that_is_both_withdrawal_and_deposit(self, tmp_path):
        path = tmp_path / "mufg_bad.csv"
        path.write_text(
            "date,withdrawal,deposit,description,balance,memo\n2026-01-05,100,200,X,1,\n",
            encoding="utf-8",
        )
        with pytest.raises(MoneyError, match="both a withdrawal and a deposit"):
            parse_file(path)

    def test_rejects_a_non_iso_date(self, tmp_path):
        path = tmp_path / "mufg_bad.csv"
        path.write_text(
            "date,withdrawal,deposit,description,balance,memo\n2026/01/05,100,,X,1,\n",
            encoding="utf-8",
        )
        with pytest.raises(MoneyError, match="YYYY-MM-DD"):
            parse_file(path)


class TestDetection:
    def test_picks_the_parser_from_the_header(self, rakuten_csv, manual_csv):
        assert detect(read_text(rakuten_csv)).NAME == "rakuten_bank"
        assert detect(read_text(manual_csv)).NAME == "manual"

    def test_unknown_header_is_refused_by_name(self, tmp_path):
        path = tmp_path / "mystery.csv"
        path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        with pytest.raises(MoneyError, match="no parser recognizes"):
            parse_file(path)


class TestEncodingGuard:
    def test_refuses_a_file_whose_characters_were_already_lost(self, tmp_path):
        # Every arithmetic check still passes on a file like this — the numbers
        # survive and only the names are gone — so this is the one guard that
        # stops it being imported and silently defeating categorization.
        damaged = "取引日,入出金(円),取引後残高(円),入出金内容\r\n20260105,1,1,��\r\n"
        path = tmp_path / "damaged.csv"
        path.write_bytes(damaged.encode("utf-8"))
        with pytest.raises(MoneyError, match="replacement characters"):
            parse_file(path)

    def test_utf8_is_tried_before_cp932(self, manual_csv):
        # CP932 would happily decode a UTF-8 file into kanji garbage, so the
        # order here is what keeps a healthy file readable.
        assert "ヤマダ" in read_text(manual_csv)
