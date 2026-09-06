from src.money.normalize import (
    has_mojibake,
    match_key,
    normalize_description,
    transaction_id,
)


class TestNormalizeDescription:
    def test_composes_a_separated_voiced_mark(self):
        # Statements send U+309B as its own character; NFKC alone would leave
        # "セ゛" and even insert a space.
        assert normalize_description("セ゛ンホケン") == "ゼンホケン"

    def test_composes_a_separated_semi_voiced_mark(self):
        assert normalize_description("ホ゜イント") == "ポイント"

    def test_folds_full_width_letters_and_digits(self):
        assert normalize_description("ＤＦ．ＡＢ２") == "DF.AB2"

    def test_restores_long_mark_after_katakana(self):
        # NFKC turns the full-width hyphen into "-", which makes katakana
        # unreadable; only the one following katakana is put back.
        assert normalize_description("マ－ケテインク") == "マーケテインク"

    def test_leaves_hyphen_alone_outside_katakana(self):
        assert normalize_description("ＡＢ－１") == "AB-1"

    def test_collapses_ideographic_spaces(self):
        assert normalize_description("ヤマダ　タロウ") == "ヤマダ タロウ"


class TestMatchKey:
    def test_enlarges_small_kana_so_natural_spelling_matches(self):
        assert match_key("ラッキーホケン") == match_key("ラツキーホケン")

    def test_strips_billing_period_suffix(self):
        # Without this, a utility charge looks like a new counterparty every
        # month and never reaches the recurrence threshold.
        assert match_key("ミナミガス　６月分") == match_key("ミナミガス　12月分")

    def test_strips_year_month_suffix(self):
        assert match_key("デンキ 26年 7月") == match_key("デンキ")

    def test_ignores_long_marks_and_spacing(self):
        assert match_key("サ－ビス　リヨウ") == match_key("サービスリヨウ")

    def test_keeps_distinct_counterparties_apart(self):
        assert match_key("ミナミガス") != match_key("デンリヨク")


class TestHasMojibake:
    def test_detects_replacement_character(self):
        assert has_mojibake("��マ") is True

    def test_healthy_text_passes(self):
        assert has_mojibake("ミナミガス 6月分") is False


class TestTransactionId:
    def test_is_stable_for_the_same_row(self):
        args = ("rakuten_bank", "2026-01-27", -12000, "ゼンホケン", 1288000)
        assert transaction_id(*args) == transaction_id(*args)

    def test_balance_separates_two_otherwise_identical_rows(self):
        # A statement really does show the same amount to the same counterparty
        # twice in one day; the running balance is the only thing that tells
        # them apart, so dropping it from the key would lose a real row.
        first = transaction_id("mufg", "2026-01-25", -10000, "WALLET", 940000)
        second = transaction_id("mufg", "2026-01-25", -10000, "WALLET", 930000)
        assert first != second

    def test_different_accounts_do_not_collide(self):
        assert transaction_id("a", "2026-01-25", -10000, "X", 1) != transaction_id(
            "b", "2026-01-25", -10000, "X", 1
        )
