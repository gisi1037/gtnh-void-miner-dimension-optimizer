# GTNH Void Miner Dimension Optimizer

Find the **fewest dimensions** needed to obtain every ore available under your chosen restrictions. Uses an **exact minimum set-cover solver**, not a greedy approximation.

**Python 3.10+ · No extra packages · Runs offline · Deep Dark always excluded**

## Download and run

Use **Code → Download ZIP**, extract the entire folder, and keep the Python files and `vmweights.csv` together.

**Windows:** double-click `run_windows.bat`. It asks for your current maximum rocket tier, remembers the answer, saves `my_result.json` and `my_result_coverage.csv`, and keeps the window open. Press Enter to keep the saved tier, or enter `all` to remove the tier limit.

Alternatively:

```powershell
py -3 ore_dimension_optimizer.py
```

On macOS/Linux, use `python3` instead of `py -3`. There is no `pip install` step.

## Set your current rocket tier

```powershell
py -3 ore_dimension_optimizer.py --set-tier 3
```

This saves your maximum tier in `settings.json` beside the program and immediately optimizes using only dimensions labeled T3 or below. Future runs automatically reuse it:

```json
{
  "max_rocket_tier": 3
}
```

The shipped setting is `null`, meaning no tier limit. Tier 0 is supported. A missing settings file means no limit; malformed settings produce an error instead of being silently ignored.

| Action | Option |
| --- | --- |
| Save your tier and optimize | `--set-tier 3` |
| Override the saved tier for one run | `--max-tier 5` |
| Ignore the saved limit for one run | `--max-tier all` |
| Clear the saved limit | `--set-tier all` |
| Ask for the tier interactively | `--choose-tier` |
| Use another settings file | `--settings path/to/settings.json` |

**The filter uses the spreadsheet's `(Tn)` labels.** It does not inspect your game or model other dimension-access requirements. Use `--exclude` for a dimension you cannot access. Deep Dark is excluded at every tier.

## Results for the bundled data

| Restriction | Obtainable ores | Unavailable ores | Exact minimum dimensions |
| --- | ---: | ---: | ---: |
| No tier limit, excluding Deep Dark | 261 | 58 | **12** |
| Maximum tier T3, excluding Deep Dark | 176 | 143 | **9** |

There are 319 listed ores and 42 dimensions in the source table. **Covering all 319 without Deep Dark is impossible in this data.** The default mode lists unavailable ores and finds the minimum for all remaining obtainable ores. Add `--strict` to require every original ore instead; it returns an explicit infeasibility result.

One unrestricted optimal set:

```text
Overworld (T0)          The End (T0)
Callisto (T3)           Ross128b (T3)
Io (T4)                Ross128ba (T5)
Toxic Everglades (T6)   Vega B (T8)
Horus (T9)             Maahes (T9)
Neper (T9)             Seth (T9)
```

All **14** equally small unrestricted solutions are in [`results.json`](results.json). [`results_coverage.csv`](results_coverage.csv) lists every ore and its sources in one selected solution. These are unrestricted examples, not your personal tier-limited reports.

## Other options

```powershell
# Print every equally small optimal combination
py -3 ore_dimension_optimizer.py --all-solutions

# Save this run's JSON and per-ore CSV reports
py -3 ore_dimension_optimizer.py --report-prefix my_result

# Exclude an additional dimension; repeat the option as needed
py -3 ore_dimension_optimizer.py --exclude "Toxic Everglades"

# Require all listed ores, even those unavailable under your restrictions
py -3 ore_dimension_optimizer.py --strict

# Recalculate using a newer CSV exported from VMWeights
py -3 ore_dimension_optimizer.py --csv updated_weights.csv

# Show valid dimension names
py -3 ore_dimension_optimizer.py --list-dimensions
```

The default retains up to 20 optimal sets and prints one. `--all-solutions` removes that output cap. The minimum is proved before the output cap is applied.

## Scope and data source

Any **positive raw weight** counts as availability. The objective is dimension count, not ore production rate, travel time, power consumption, or the number of miners. Very rare positive weights still count.

`vmweights.csv` is the **November 17, 2026** snapshot of `VMWeights!A1:AQ321` from the community spreadsheet **Void Miner probabilities by Ore or Dimension**, whose front page is labeled **GTNE 2.8.0, v5**:

- [Source spreadsheet / lookup](https://docs.google.com/spreadsheets/d/1vepnwZw611GSojAOKc0yfj3J4dd1nFpxsucGuf373GU/edit?gid=692792068)
- [Underlying VMWeights table](https://docs.google.com/spreadsheets/d/1vepnwZw611GSojAOKc0yfj3J4dd1nFpxsucGuf373GU/edit?gid=0)

These results describe that snapshot, **not a verified current GTNH ore registry**, and do not imply an ore cannot be obtained through other mining or processing methods.

To update, export the **VMWeights** tab as CSV: ore names in column A, dimension names in row 1 starting at B, and numeric weights elsewhere. Blank numeric cells mean zero. Optional SUM/Total/Totals rows are validated and excluded from the ore count. Duplicate names, invalid weights, and mismatched totals are rejected. The program does not automatically fetch data from the internet.

## Solver and tests

The solver uses integer bitsets, exclusive-ore constraints, a memoized exact search with valid bounds, and a separate search to enumerate tied optima. A greedy cover supplies an upper bound only; it is never reported as a proved minimum by itself.

Eight dimensions are mandatory in the unrestricted snapshot. They cover 231 ores, leaving 30; at least four additional dimensions are needed. The resulting minimum is **8 + 4 = 12**.

```powershell
py -3 -m unittest discover -v
```

The 21 tests include 400 seeded comparisons against independent brute-force enumeration, snapshot results, CSV validation, strict infeasibility, saved rocket tiers, one-run overrides, reset behavior, and interactive input. GitHub Actions runs the suite on Windows and Linux.

Core files: `ore_dimension_optimizer.py` (settings, CLI, parsing and reports), `solver.py` (exact solver), `vmweights.csv` (snapshot), `settings.json` (your saved tier), and `run_windows.bat` (launcher).

Exit codes: **0** optimum found; **1** input/file error; **2** strict coverage impossible (or invalid command-line arguments); **130** cancelled.
