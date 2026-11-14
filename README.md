# FAA attribution price forecaster

An entry for the make.fun bounty
[polymarket-faa-attribution-02](https://make.fun/bounty/polymarket-faa-attribution-02):
forecast the Yes price of Polymarket's four FAA outage attribution markets (Iran, a foreign
actor, a hack, an AI sandbox escape) at every minute of the 4 hours after a checkpoint.

## What it does

For each case file (`*.in`, JSON with each market's 1-minute Yes price history up to a
checkpoint), `main.py` writes a `.out` file with, for every market and each of the 240
minutes after the checkpoint, five quantiles (5%, 25%, 50%, 75%, 95%) of that minute's price:

```
{"forecasts":[{"id":"0x…","q":[[0.0205,0.021,0.021,0.021,0.0215], …240 rows…]}, …]}
```

The model, per market, works in logit space, which keeps every quantile inside (0, 1) and
skews the fan correctly for markets priced near 0:

- **Median**: the last price. Drifts and reversions toward recent levels were tried and lost.
- **Volatility fan**: a robust volatility of 1-minute logit moves (outliers clipped, short and
  long windows mixed), shrunk toward a fixed prior, widening as h^0.3 (thin books flip back
  and forth more than they trend) and opening slower over the first hour.
- **Empirical changes**: recency-weighted quantiles of the market's own h-minute logit
  changes, blended in at 20%. Where they say the price is most likely unchanged, the 25% and
  75% quantiles stay on the last price, which is what pinball loss rewards for a market that
  rarely ticks.
- **Skewed tails**: the 5% tail is widened and the 95% tail narrowed a little, because
  low-priced long shots drift down more often than they jump.

The constants were chosen on a local benchmark of hourly 4-hour cases cut from the FAA
markets' own 1-minute history (after the launch burst), plus the low-priced markets of the
"Next CEO of NVIDIA?" event as a calmer regime, scored with the exact pinball loss.

## How it is scored

Mean pinball loss (in percentage points) over every case, market, minute and quantile, against
the actual Polymarket grid price. The final is twelve 4-hour cases covering the 48 hours after
2026-11-14 14:00 UTC; lower is better.

## Run it locally

Python 3.13, standard library only:

```
mkdir out
MAKEFUN_INPUT_DIR=path/to/cases MAKEFUN_OUTPUT_DIR=out python3 main.py
```
