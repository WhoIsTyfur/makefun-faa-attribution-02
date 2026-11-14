"""Quantile fan forecast for Polymarket price paths (make.fun polymarket-faa-attribution-02).

Reads every *.in case in $MAKEFUN_INPUT_DIR (default /input), writes one .out per case
to $MAKEFUN_OUTPUT_DIR (default /output). Standard library only, deterministic.

Model, per market, all in logit space (bounded in (0, 1), skewed for prices near 0):
  1. a volatility fan: robust volatility of 1-minute logit changes (each move clipped at
     CLIP x the median nonzero move, so a launch burst does not dominate), mixing a short
     and a long window, spread over the horizon as h^EXPO (sub-diffusive: thin books flip
     back and forth more than they trend); the 25/75% quantiles are scaled by how often the
     book ticks at all, so a market that rarely moves keeps its inner quantiles near the
     last price, which is what pinball loss rewards;
  2. empirical quantiles of the market's own h-minute logit changes, recency weighted;
  3. the forecast is W x (1) + (1 - W) x (2), quantile by quantile.
The median is the last price: on these markets it beat every drift or reversion tried.
The volatility is shrunk toward a fixed prior (S0, PW), and the outer tails are skewed:
low-priced long shots drift down more often than they jump up.
"""
import bisect
import json
import math
import os

TAUS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.644854, -0.674490, 0.0, 0.674490, 1.644854)

# fan
WIN, LWIN, MIX = 180, 720, 0.6
EXPO, INNER, CLIP = 0.3, 0.3, 10.0
# empirical
EWIN, HALF = 720, 240.0
HS = (1, 2, 4, 8, 15, 30, 60, 120, 240)
# prior logit volatility the market's own is shrunk toward (variance weight PW)
S0, PW = 0.1, 0.6
# blend, then outer tails: down tail x DM, up tail x UM (long shots decay more than they jump)
W = 0.8
DM, UM = 1.2, 0.7
# the fan opens slower than h^EXPO over the first RAMP_H minutes: x (h / RAMP_H)^RAMP_G
RAMP_H, RAMP_G = 60, 0.5


def lg(v):
    v = min(max(v, 1e-4), 1 - 1e-4)
    return math.log(v / (1 - v))


def ilg(u):
    if u < -30:
        return 0.0
    return 1 / (1 + math.exp(-u))


def robust_sigma(d):
    """RMS of moves clipped at CLIP x median nonzero move; also share of minutes that moved."""
    n = max(1, len(d))
    nz = sorted(abs(v) for v in d if v != 0)
    if not nz:
        return 0.0, 0.0
    cap = CLIP * nz[len(nz) // 2]
    return math.sqrt(sum(min(abs(v), cap) ** 2 for v in d) / n), len(nz) / n


def fan(u, horizon):
    d = [b - a for a, b in zip(u, u[1:])]
    s1, sh1 = robust_sigma(d[-WIN:])
    s2, sh2 = robust_sigma(d[-LWIN:])
    s = math.sqrt(MIX * s1 * s1 + (1 - MIX) * s2 * s2)
    s = math.sqrt((1 - PW) * s * s + PW * S0 * S0)
    kin = min(1.0, INNER + MIX * sh1 + (1 - MIX) * sh2)
    ux = u[-1]
    rows = []
    for h in range(1, horizon + 1):
        sd = s * h ** EXPO
        rows.append([ux + z * sd * (kin if i in (1, 3) else 1.0) for i, z in enumerate(Z)])
    return rows


def wquant(pairs):
    pairs.sort()
    tw = sum(w for _, w in pairs)
    out, acc, j = [], 0.0, 0
    for t in TAUS:
        target = t * tw
        while j < len(pairs) - 1 and acc + pairs[j][1] < target:
            acc += pairs[j][1]
            j += 1
        out.append(pairs[j][0])
    return out


def empirical(u, horizon):
    u = u[-(EWIN + 241):]
    n = len(u)
    ux = u[-1]
    table = []
    for h in HS:
        pairs = []
        for i in range(max(0, n - 1 - EWIN), n - h):
            age = n - 1 - (i + h)
            pairs.append((u[i + h] - u[i], 0.5 ** (age / HALF)))
        if len(pairs) < 5:
            pairs = [(0.0, 1.0)]
        table.append(wquant(pairs))
    rows = []
    for h in range(1, horizon + 1):
        j = bisect.bisect_left(HS, h)
        if j == 0:
            qs = table[0]
        elif j >= len(HS):
            qs = table[-1]
        else:
            h0, h1 = HS[j - 1], HS[j]
            w = (math.log(h) - math.log(h0)) / (math.log(h1) - math.log(h0))
            qs = [a + w * (b - a) for a, b in zip(table[j - 1], table[j])]
        rows.append([ux + c for c in qs])
    return rows


def forecast_market(prices, horizon):
    prices = [float(v) for v in prices if v is not None]
    if not prices:
        return [[0.5] * 5 for _ in range(horizon)]
    x = prices[-1]
    if len(prices) < 3:
        return [[min(1.0, max(0.0, round(x + z * 0.0025 * math.sqrt(h), 6))) for z in Z]
                for h in range(1, horizon + 1)]
    u = [lg(v) for v in prices[-(max(LWIN, EWIN + 240) + 1):]]
    a = fan(u, horizon)
    b = empirical(u, horizon)
    ux = u[-1]
    rows = []
    for h, (ra, rb) in enumerate(zip(a, b), 1):
        if h < RAMP_H:
            f = (h / RAMP_H) ** RAMP_G
            ra = [ux + f * (v - ux) for v in ra]
        r = [W * ilg(p) + (1 - W) * ilg(q) for p, q in zip(ra, rb)]
        r[0] = x - DM * (x - r[0])
        r[4] = x + UM * (r[4] - x)
        r[2] = x
        # the market's own history says "unchanged" at this quantile: keep it on the price
        for i in (1, 3):
            if rb[i] == ux:
                r[i] = x
        r = [min(1.0, max(0.0, round(v, 6))) for v in r]
        for i in range(1, 5):
            if r[i] < r[i - 1]:
                r[i] = r[i - 1]
        rows.append(r)
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
            try:
                q = forecast_market(m["prices"], horizon)
            except Exception:
                x = float(m["prices"][-1])
                q = [[min(1.0, max(0.0, round(x + z * 0.0025 * math.sqrt(h), 6))) for z in Z]
                     for h in range(1, horizon + 1)]
            out.append({"id": m["id"], "q": q})
        with open(os.path.join(out_dir, name[:-3] + ".out"), "w", encoding="utf-8") as f:
            json.dump({"forecasts": out}, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
