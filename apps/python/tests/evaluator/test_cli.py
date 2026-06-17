from unittest.mock import patch

from src.evaluator.__main__ import main


def test_main_extract_dispatches_target():
    with patch("src.evaluator.__main__.extract.extract") as m:
        assert main(["extract", "2026-06-17"]) == 0
    m.assert_called_once_with("2026-06-17")


def test_main_extract_defaults_to_all():
    with patch("src.evaluator.__main__.extract.extract") as m:
        assert main(["extract"]) == 0
    m.assert_called_once_with("all")


def test_main_report_dispatches():
    with patch("src.evaluator.__main__.report.build_report") as m:
        assert main(["report"]) == 0
    m.assert_called_once_with()
