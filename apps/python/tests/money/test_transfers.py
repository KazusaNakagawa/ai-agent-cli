from src.money.models import Transaction
from src.money.normalize import match_key, normalize_description
from src.money.parsers import parse_file
from src.money.rules import Rules, make_matcher
from src.money.transfers import (
    apply_transfer_rules,
    pair_cross_account,
    unpaired_transfer_candidates,
)


def _tx(tid, date, account, amount, desc="X"):
    return Transaction(
        id=tid,
        date=date,
        account=account,
        amount=amount,
        desc_raw=desc,
        desc=normalize_description(desc),
        desc_key=match_key(desc),
    )


class TestPairing:
    def test_matches_opposite_halves_across_accounts(self):
        rows = pair_cross_account(
            [_tx("a", "2026-01-05", "mufg", -300000), _tx("b", "2026-01-05", "rakuten", 300000)]
        )
        assert [t.is_transfer for t in rows] == [True, True]
        assert rows[0].transfer_peer == "b" and rows[1].transfer_peer == "a"

    def test_tolerates_a_settlement_lag_of_a_day(self):
        rows = pair_cross_account(
            [_tx("a", "2026-01-05", "mufg", -300000), _tx("b", "2026-01-06", "rakuten", 300000)]
        )
        assert all(t.is_transfer for t in rows)

    def test_ignores_a_gap_beyond_the_window(self):
        rows = pair_cross_account(
            [_tx("a", "2026-01-05", "mufg", -300000), _tx("b", "2026-01-20", "rakuten", 300000)]
        )
        assert not any(t.is_transfer for t in rows)

    def test_never_pairs_within_one_account(self):
        rows = pair_cross_account(
            [_tx("a", "2026-01-05", "mufg", -300000), _tx("b", "2026-01-05", "mufg", 300000)]
        )
        assert not any(t.is_transfer for t in rows)

    def test_each_half_is_used_once(self):
        # Two identical outgoing transfers must not both claim the single
        # incoming one, or a real expense would vanish.
        rows = pair_cross_account(
            [
                _tx("a", "2026-01-05", "mufg", -300000),
                _tx("b", "2026-01-05", "mufg", -300000),
                _tx("c", "2026-01-05", "rakuten", 300000),
            ]
        )
        assert sum(t.is_transfer for t in rows) == 2

    def test_prefers_the_same_day_candidate(self):
        rows = pair_cross_account(
            [
                _tx("out", "2026-01-05", "mufg", -300000),
                _tx("far", "2026-01-07", "rakuten", 300000),
                _tx("near", "2026-01-05", "rakuten", 300000),
            ]
        )
        assert {t.id: t.transfer_peer for t in rows}["out"] == "near"

    def test_equally_close_candidates_do_not_depend_on_row_order(self):
        # Both candidates sit one day away, so ranking on the gap alone would
        # let the order the files happened to be imported in decide which
        # transaction stops counting as spending.
        out = _tx("out", "2026-01-05", "mufg", -300000)
        earlier = _tx("earlier", "2026-01-04", "rakuten", 300000)
        later = _tx("later", "2026-01-06", "rakuten", 300000)
        for order in ([out, earlier, later], [out, later, earlier]):
            rows = pair_cross_account(order)
            assert {t.id: t.transfer_peer for t in rows}["out"] == "earlier"


class TestRules:
    def test_flags_a_counterparty_whose_other_side_is_not_imported(self):
        rules = Rules(transfer_patterns=[make_matcher("シヨウケンガイシヤ", where="t")])
        rows = apply_transfer_rules([_tx("a", "2026-02-10", "rakuten", -800000, "シヨウケンガイシヤ")], rules)
        assert rows[0].is_transfer is True

    def test_flags_a_transfer_to_your_own_name(self):
        rules = Rules(self_names=[match_key("ヤマダ　タロウ")])
        rows = apply_transfer_rules([_tx("a", "2026-01-05", "mufg", -300000, "振込ＩＢ２　ヤマダ　タロウ")], rules)
        assert rows[0].is_transfer is True

    def test_your_name_as_requester_is_not_a_transfer(self):
        # Every outgoing transfer records the sender — you — next to the
        # recipient. Matching on that would file rent as an internal move and
        # silently erase it from spending, which is exactly what happened on
        # real data before the counterparty portion was isolated.
        rules = Rules(self_names=[match_key("ヤマダ　タロウ")])
        rent = _tx(
            "a",
            "2026-05-02",
            "rakuten",
            -90000,
            "銀行　支店　普通預金　0000000　カ）フドウサン（依頼人名：ヤマタ゛　タロウ　振込予定日：2026年05月02日）",
        )
        assert apply_transfer_rules([rent], rules)[0].is_transfer is False

    def test_your_name_as_recipient_is_still_a_transfer(self):
        # The same annotation appears when you really do move money to your own
        # account elsewhere — but there your name is the recipient too.
        rules = Rules(self_names=[match_key("ヤマダ　タロウ")])
        move = _tx(
            "a",
            "2026-05-02",
            "rakuten",
            -90000,
            "銀行　支店　普通預金　0000000　ヤマダ　タロウ（依頼人名：ヤマダ　タロウ）",
        )
        assert apply_transfer_rules([move], rules)[0].is_transfer is True

    def test_removing_a_rule_clears_the_flag(self):
        # The flag is recomputed rather than accumulated, so a rule deleted from
        # the config actually takes effect instead of being remembered forever
        # by the stored rows.
        flagged = apply_transfer_rules(
            [_tx("a", "2026-02-10", "rakuten", -800000, "シヨウケンガイシヤ")],
            Rules(transfer_patterns=[make_matcher("シヨウケンガイシヤ", where="t")]),
        )
        assert flagged[0].is_transfer is True
        assert apply_transfer_rules(flagged, Rules())[0].is_transfer is False

    def test_leaves_ordinary_spending_alone(self):
        rules = Rules(transfer_patterns=[make_matcher("シヨウケンガイシヤ", where="t")])
        rows = apply_transfer_rules([_tx("a", "2026-01-27", "rakuten", -12000, "ホケン")], rules)
        assert rows[0].is_transfer is False


class TestReview:
    def test_transfers_without_a_pair_are_surfaced(self, rakuten_csv, rules):
        # With only one account imported, neither transfer can be paired: the
        # brokerage is never imported, and the other bank has not been yet.
        # Reporting both is right — silence would look like everything matched.
        rows = pair_cross_account(apply_transfer_rules(parse_file(rakuten_csv).transactions, rules))
        assert [t.desc for t in unpaired_transfer_candidates(rows)] == [
            "ヤマダ タロウ",
            "シヨウケンガイシヤ",
        ]

    def test_the_list_shrinks_once_the_other_account_arrives(self, rakuten_csv, manual_csv, rules):
        # Only the brokerage transfer should remain: its counterparty is an
        # account that will never be imported, so a rule is the only handle.
        rows = parse_file(rakuten_csv).transactions + parse_file(manual_csv).transactions
        rows = pair_cross_account(apply_transfer_rules(rows, rules))
        assert [t.desc for t in unpaired_transfer_candidates(rows)] == ["シヨウケンガイシヤ"]
