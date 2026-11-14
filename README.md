# FAA attribution price forecaster

An entry for the make.fun bounty
[polymarket-faa-attribution-02](https://make.fun/bounty/polymarket-faa-attribution-02).

## What it does

For each case file (`*.in`, JSON with each market's 1-minute Yes price history up to a
checkpoint), `main.py` writes a `.out` file with, for every market and each of the 240
minutes after the checkpoint, five quantiles (5%, 25%, 50%, 75%, 95%) of that minute's price:

```
{"forecasts":[{"id":"0x…","q":[[0.0281,0.0285,0.0285,0.0285,0.0290], …240 rows…]}, …]}
```

The median sits at the last price; the spread around it comes from each market's own
recent price behaviour (see the code comments for the current model).

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
