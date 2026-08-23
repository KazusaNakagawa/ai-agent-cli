import json

import pytest

from src.money.categorize import categorize, uncategorized
from src.money.models import UNCATEGORIZED, MoneyError, Transaction
from src.money.normalize import match_key, normalize_description
from src.money.rules import load_rules


def _tx(desc, amount=-1000, account="rakuten_bank"):
    return Transaction(
        id=desc,
        date="2026-01-27",
        account=account,
        amount=amount,
        desc_raw=desc,
        desc=normalize_description(desc),
        desc_key=match_key(desc),
    )


def _write_rules(tmp_path, payload):
    path = tmp_path / "money_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TestBuiltins:
    def test_work_without_any_config_file(self):
        rules = load_rules(None)
        assert categorize([_tx("給料", 250000)], rules)[0].category == "income_salary"

    def test_interest_wins_over_bonus_wording(self):
        # A bank pays "ボーナス金利利息" — bonus-rate interest. Matching that as a
        # salary bonus would move it into the wrong income category, so the
        # interest rule is ordered first.
        rules = load_rules(None)
        row = _tx("口座振替（楽天カ－ド以外の引き落とし：1-2件）ボ－ナス金利利息", 7)
        assert categorize([row], rules)[0].category == "income_interest"

    def test_an_unknown_counterparty_stays_visible(self):
        rules = load_rules(None)
        assert categorize([_tx("ＤＦ．ＡＢＣショウカイ")], rules)[0].category == UNCATEGORIZED


class TestUserRules:
    def test_a_natural_spelling_matches_the_bank_spelling(self, tmp_path):
        # The bank writes full-size kana. Without folding the pattern the same
        # way as the description, a rule written normally would never fire.
        path = _write_rules(
            tmp_path, {"categories": [{"pattern": "ラッキーホケン", "category": "insurance"}]}
        )
        rules = load_rules(path)
        assert categorize([_tx("ラツキーホケンＡＰＳ")], rules)[0].category == "insurance"

    def test_a_regex_pattern_still_works(self, tmp_path):
        path = _write_rules(
            tmp_path, {"categories": [{"pattern": "ガス|デンキ", "category": "utility"}]}
        )
        rules = load_rules(path)
        assert categorize([_tx("ミナミガス　6月分")], rules)[0].category == "utility"

    def test_user_rules_take_precedence_over_builtins(self, tmp_path):
        path = _write_rules(
            tmp_path, {"categories": [{"pattern": "利息", "category": "custom_interest"}]}
        )
        rules = load_rules(path)
        assert categorize([_tx("預金利息", 500)], rules)[0].category == "custom_interest"

    def test_comment_keys_do_not_become_rules(self, tmp_path):
        # The shipped example documents itself with "_"-prefixed entries; a
        # copied config must not turn its own comments into matchers.
        path = _write_rules(
            tmp_path,
            {
                "accounts": {"_comment": "docs", "mufg": {"label": "三菱UFJ銀行"}},
                "self_names": ["_comment: docs", "ヤマダ タロウ"],
                "transfer_patterns": ["_comment: docs", "ショウケン"],
            },
        )
        rules = load_rules(path)
        assert "_comment" not in rules.accounts
        assert len(rules.self_names) == 1
        assert len(rules.transfer_patterns) == 1

    def test_a_broken_pattern_names_the_file(self, tmp_path):
        path = _write_rules(
            tmp_path, {"categories": [{"pattern": "[unclosed", "category": "x"}]}
        )
        with pytest.raises(MoneyError, match="invalid regular expression"):
            load_rules(path)

    def test_malformed_json_is_reported_not_raised_raw(self, tmp_path):
        path = tmp_path / "money_rules.json"
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(MoneyError, match="not valid JSON"):
            load_rules(path)

    def test_valid_json_of_the_wrong_shape_is_reported_too(self, tmp_path):
        # A file can parse and still be nothing this can read. Without the
        # shape check the CLI prints an AttributeError traceback, which says
        # nothing about the line the person edited.
        path = tmp_path / "money_rules.json"
        path.write_text('["a", "b"]', encoding="utf-8")
        with pytest.raises(MoneyError, match="must be a JSON object"):
            load_rules(path)

    def test_a_section_of_the_wrong_type_names_the_key(self, tmp_path):
        path = _write_rules(tmp_path, {"self_names": "ヤマダ タロウ"})
        with pytest.raises(MoneyError, match="'self_names' must be a list"):
            load_rules(path)

    def test_a_non_text_entry_names_the_key(self, tmp_path):
        path = _write_rules(tmp_path, {"transfer_patterns": [123]})
        with pytest.raises(MoneyError, match="'transfer_patterns' must be text"):
            load_rules(path)

    def test_a_category_rule_that_is_not_an_object_is_refused(self, tmp_path):
        path = _write_rules(tmp_path, {"categories": ["ホケン"]})
        with pytest.raises(MoneyError, match="must be an object"):
            load_rules(path)


class TestReviewList:
    def test_transfers_are_not_asked_about(self):
        # A transfer is already explained; listing it as unclassified would
        # bury the rows that genuinely need a rule.
        rules = load_rules(None)
        rows = categorize([_tx("シヨウケン")], rules)
        rows = [rows[0].with_(is_transfer=True)]
        assert uncategorized(rows) == []
