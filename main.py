"""Quantile fan forecast for Polymarket price paths (make.fun polymarket-faa-attribution-02).

Reads every *.in case in $MAKEFUN_INPUT_DIR (default /input), writes one .out per case
to $MAKEFUN_OUTPUT_DIR (default /output). Standard library only, deterministic.
"""
import json
import math
import os

Z = (-1.644854, -0.674490, 0.0, 0.674490, 1.644854)


def recent_sigma(prices, window=720):
    """Per-sqrt-minute volatility from the last `window` one-minute changes."""
    p = prices[-(window + 1):]
    if len(p) < 3:
        return 0.0025
    ss = 0.0
    for a, b in zip(p, p[1:]):
        ss += (b - a) ** 2
    return math.sqrt(ss / (len(p) - 1))


def forecast_market(prices, horizon):
    x = prices[-1]
    s = recent_sigma(prices)
    s = min(max(s, 0.0003), 0.01)
    rows = []
    for h in range(1, horizon + 1):
        sd = s * math.sqrt(h)
        row = [min(1.0, max(0.0, round(x + z * sd, 6))) for z in Z]
        rows.append(row)
    return rows


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    for name in sorted(os.listdir(in_dir)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(in_dir, name), encoding="utf-8") as f:
            case = json.load(f)
        horizon = int(case.get("horizon_minutes", 240))
        out = []
        for m in case["markets"]:
            out.append({"id": m["id"], "q": forecast_market(m["prices"], horizon)})
        with open(os.path.join(out_dir, name[:-3] + ".out"), "w", encoding="utf-8") as f:
            json.dump({"forecasts": out}, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
