import yfinance as yf
from src.logger import get_logger

logger = get_logger(__name__)


def fetch_stock_move_map(tickers: list[str]) -> dict[str, str]:
    """yfinance で前日比を取得し、ticker → 表示文字列の dict で返す (#152)。

    ローカル LLM 経路の保有銘柄テーブルは Python 側でセルを埋めるため、
    結合済み文字列ではなく per-ticker の値が要る。取得失敗はエラー文字列を
    入れて呼び出し側に判断を委ねる (テーブル側は出典セル同様 `-` 等で表示)。
    """
    moves: dict[str, str] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            pct = (info.last_price / info.previous_close - 1) * 100
            arrow = "↑" if pct > 0 else "↓"
            moves[t] = f"{arrow}{abs(pct):.1f}%  (${info.last_price:.2f})"
            logger.debug("株価取得: %s: %s", t, moves[t])
        except Exception as e:
            logger.warning("株価取得失敗 [%s]: %s", t, e)
            moves[t] = f"取得エラー ({e})"
    return moves


def fetch_stock_moves(tickers: list[str]) -> str:
    """yfinance で前日比を取得（無料）"""
    return "\n".join(
        f"{t}: {move}" for t, move in fetch_stock_move_map(tickers).items()
    )
