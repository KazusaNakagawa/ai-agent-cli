import requests
from src.logger import get_logger

logger = get_logger(__name__)


def send_to_discord(text: str, token: str, channel_id: str):
    """Discord Bot API でチャンネルにメッセージ送信（2000文字制限を考慮して分割）"""
    if not token or not channel_id:
        logger.error("DISCORD_TOKEN または CHANNEL_ID が未設定")
        return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    chunk_size = 1900
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    for i, chunk in enumerate(chunks, 1):
        res = requests.post(url, headers=headers, json={"content": chunk})
        res.raise_for_status()
        logger.debug("Discord 送信完了 (chunk %d/%d)", i, len(chunks))
    logger.info("Discord 送信完了 (合計%dチャンク)", len(chunks))
