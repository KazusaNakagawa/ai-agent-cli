from unittest.mock import MagicMock, patch

from src import self_agent_handler


def _config(notion_ok: bool):
    cfg = MagicMock()
    cfg.notion_api_key = "key" if notion_ok else ""
    cfg.notion_database_id = "db" if notion_ok else ""
    return cfg


def test_run_skips_when_no_new_entries(tmp_path):
    with patch.object(self_agent_handler, "fetch_new_entries", return_value=[]) as mock_fetch, \
         patch.object(self_agent_handler, "write_watermark") as mock_write_wm, \
         patch.object(self_agent_handler, "send_to_notion") as mock_notion:
        result = self_agent_handler.run(
            profile_path=tmp_path / "profile.md", output_dir=tmp_path / "out"
        )
    assert result == {"status": "skipped", "reason": "no new entries"}
    mock_fetch.assert_called_once()
    mock_write_wm.assert_not_called()
    mock_notion.assert_not_called()


def test_run_writes_report_and_delivers_to_notion(tmp_path):
    profile_path = tmp_path / "profile.md"
    output_dir = tmp_path / "out"
    entries = [{"id": "j_1"}, {"id": "j_2"}]

    with patch.object(self_agent_handler, "fetch_new_entries", return_value=entries), \
         patch.object(self_agent_handler, "generate_self_profile_update", return_value=("report body", "diff body")), \
         patch.object(self_agent_handler, "send_to_notion", return_value="https://notion.example/page") as mock_notion, \
         patch.object(self_agent_handler, "write_watermark") as mock_write_wm, \
         patch("src.self_agent_handler.CONFIG", _config(notion_ok=True)):
        result = self_agent_handler.run(profile_path=profile_path, output_dir=output_dir)

    assert result["status"] == "ok"
    assert result["notion_url"] == "https://notion.example/page"
    report_path = list(output_dir.glob("self_agent_report_*.md"))[0]
    assert report_path.read_text(encoding="utf-8") == "report body"
    assert profile_path.read_text(encoding="utf-8") == "\n\ndiff body\n"
    mock_notion.assert_called_once()
    mock_write_wm.assert_called_once_with("j_2")


def test_run_preserves_local_report_when_notion_delivery_fails(tmp_path):
    profile_path = tmp_path / "profile.md"
    output_dir = tmp_path / "out"
    entries = [{"id": "j_1"}]

    with patch.object(self_agent_handler, "fetch_new_entries", return_value=entries), \
         patch.object(self_agent_handler, "generate_self_profile_update", return_value=("report body", "")), \
         patch.object(self_agent_handler, "send_to_notion", side_effect=RuntimeError("boom")), \
         patch.object(self_agent_handler, "write_watermark") as mock_write_wm, \
         patch("src.self_agent_handler.CONFIG", _config(notion_ok=True)):
        result = self_agent_handler.run(profile_path=profile_path, output_dir=output_dir)

    assert result["status"] == "ok"
    report_path = list(output_dir.glob("self_agent_report_*.md"))[0]
    assert report_path.read_text(encoding="utf-8") == "report body"
    # Watermark still advances: the report was successfully produced and saved locally.
    mock_write_wm.assert_called_once_with("j_1")


def test_run_skips_notion_when_not_configured(tmp_path):
    profile_path = tmp_path / "profile.md"
    output_dir = tmp_path / "out"
    entries = [{"id": "j_1"}]

    with patch.object(self_agent_handler, "fetch_new_entries", return_value=entries), \
         patch.object(self_agent_handler, "generate_self_profile_update", return_value=("report body", "")), \
         patch.object(self_agent_handler, "send_to_notion") as mock_notion, \
         patch.object(self_agent_handler, "write_watermark"), \
         patch("src.self_agent_handler.CONFIG", _config(notion_ok=False)):
        result = self_agent_handler.run(profile_path=profile_path, output_dir=output_dir)

    assert result["status"] == "ok"
    assert result["notion_url"] == ""
    mock_notion.assert_not_called()


def test_apply_profile_diff_noop_on_empty_diff(tmp_path):
    profile_path = tmp_path / "profile.md"
    self_agent_handler._apply_profile_diff("", profile_path)
    assert not profile_path.exists()
