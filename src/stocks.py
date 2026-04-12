import yfinance as yf
from src.logger import get_logger

logger = get_logger(__name__)


def fetch_stock_moves(tickers: list[str]) -> str:
    """yfinance で前日比を取得（無料）"""
    lines = []
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            pct = (info.last_price / info.previous_close - 1) * 100
            arrow = "↑" if pct > 0 else "↓"
            line = f"{t}: {arrow}{abs(pct):.1f}%  (${info.last_price:.2f})"
            lines.append(line)
            logger.debug("株価取得: %s", line)
        except Exception as e:
            logger.warning("株価取得失敗 [%s]: %s", t, e)
            lines.append(f"{t}: 取得エラー ({e})")
    return "\n".join(lines)
