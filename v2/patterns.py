def candle_patterns(df):
    """Classic candlestick patterns on the last two candles.

    Returns {"bullish": [...names], "bearish": [...names], "neutral": [...names]}.
    """
    out = {"bullish": [], "bearish": [], "neutral": []}
    if len(df) < 2:
        return out
    prev, cur = df.iloc[-2], df.iloc[-1]
    o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
    po, ph, pl, pc = prev["open"], prev["high"], prev["low"], prev["close"]
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l

    if pc < po and c > o and c >= po and o <= pc:
        out["bullish"].append("bullish engulfing")
    if pc > po and c < o and o >= pc and c <= po:
        out["bearish"].append("bearish engulfing")
    if body / rng >= 0.1 and lower >= 2 * body and upper <= body:
        out["bullish"].append("hammer")
    if body / rng >= 0.1 and upper >= 2 * body and lower <= body:
        out["bearish"].append("shooting star")
    if body / rng < 0.1:
        out["neutral"].append("doji")
    if h < ph and l > pl:
        out["neutral"].append("inside bar")
    if c > o and body / rng >= 0.8:
        out["bullish"].append("bullish marubozu")
    if c < o and body / rng >= 0.8:
        out["bearish"].append("bearish marubozu")
    return out
