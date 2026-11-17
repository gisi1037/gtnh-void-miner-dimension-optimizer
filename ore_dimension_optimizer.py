#!/usr/bin/env python3
"""Find exact minimum dimension covers for the supplied GTNE ore weight matrix.

Python 3.10+; standard library only. Deep Dark is always excluded.
The default run explicitly reports unobtainable ores and solves for all remaining
ores. --strict instead requires every listed ore and reports infeasibility.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from solver import solve_cover


DEFAULT_CSV = Path(__file__).resolve().with_name("vmweights.csv")
DEFAULT_SETTINGS = Path(__file__).resolve().with_name("settings.json")
SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1vepnwZw611GSojAOKc0yfj3J4dd1nFpxsucGuf373GU/edit?gid=0"
)
SNAPSHOT_DATE = "2026-11-17"
BUNDLED_CSV_SHA256 = "1ef313c9cc13ea7c18e301b1f474ebc2fcd5728fc16867eea08fa1880572d9d6"


def parse_tier(value: str) -> int | None:
    """Accept a nonnegative tier or 'all' for no tier limit."""
    if value.strip().casefold() == "all":
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use a nonnegative integer or 'all'.") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("The rocket tier must be nonnegative.")
    return number


def load_settings(path: Path) -> dict:
    """A missing settings file means no tier limit; malformed files are errors."""
    if not path.exists():
        return {"max_rocket_tier": None}
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in settings file {path}: {exc.msg}") from exc
    if not isinstance(settings, dict):
        raise ValueError(f"Settings file {path} must contain a JSON object.")
    unknown = set(settings) - {"max_rocket_tier"}
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
    value = settings.get("max_rocket_tier")
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("max_rocket_tier must be a nonnegative integer or null.")
    return {"max_rocket_tier": value}


def save_settings(path: Path, settings: dict) -> None:
    """Replace settings atomically so an interrupted write cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply_settings(args: argparse.Namespace) -> None:
    settings = load_settings(args.settings)
    saved_tier = settings["max_rocket_tier"]
    if args.choose_tier:
        current = "all" if saved_tier is None else str(saved_tier)
        while True:
            try:
                answer = input(
                    f"Maximum rocket tier [current: {current}; Enter keeps it; 'all' removes limit]: "
                ).strip()
            except EOFError as exc:
                raise ValueError("No interactive input available. Use --set-tier N instead.") from exc
            if not answer:
                break
            try:
                saved_tier = parse_tier(answer)
            except argparse.ArgumentTypeError as exc:
                print(f"Invalid tier: {exc}")
                continue
            settings["max_rocket_tier"] = saved_tier
            save_settings(args.settings, settings)
            print(f"Saved rocket tier setting to {args.settings}")
            break
    elif hasattr(args, "set_tier"):
        saved_tier = args.set_tier
        settings["max_rocket_tier"] = saved_tier
        save_settings(args.settings, settings)
        print(f"Saved rocket tier setting to {args.settings}")
    # --max-tier only affects this run; it never overwrites the saved setting.
    if not hasattr(args, "max_tier"):
        args.max_tier = saved_tier


def base_name(name: str) -> str:
    """Case-insensitive dimension name without its optional tier suffix."""
    return re.sub(r"\s*\(T\d+\)\s*$", "", name, flags=re.I).strip().casefold()


def is_deep_dark(name: str) -> bool:
    return re.sub(r"[\s_-]+", "", base_name(name)) == "deepdark"


def tier(name: str) -> int:
    match = re.search(r"\(T(\d+)\)\s*$", name, flags=re.I)
    if not match:
        raise ValueError(f"Cannot apply --max-tier: no tier in {name!r}.")
    return int(match.group(1))


def read_matrix(path: Path) -> dict:
    """Read the actual VMWeights CSV layout, validating weights and totals."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or len(rows[0]) < 2:
        raise ValueError("Expected ore names in column A and dimension headers in row 1.")
    dimensions = [name.strip() for name in rows[0][1:]]
    if any(not name for name in dimensions):
        raise ValueError("A dimension header is blank. Export the VMWeights tab.")
    if len({name.casefold() for name in dimensions}) != len(dimensions):
        raise ValueError("Dimension headers must be unique.")

    weights: dict[str, dict[str, Decimal]] = {}
    source_rows: dict[str, int] = {}
    totals = [Decimal(0) for _ in dimensions]
    summary_rows = []
    seen_ores = set()
    for row_number, row in enumerate(rows[1:], 2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(dimensions) + 1:
            raise ValueError(f"Row {row_number}: expected {len(dimensions) + 1} columns, got {len(row)}.")
        ore = row[0].strip()
        if not ore:
            raise ValueError(f"Row {row_number}: missing ore name.")
        numeric = []
        for column, value in enumerate(row[1:], 2):
            try:
                number = Decimal(value.strip() or "0")
            except InvalidOperation as exc:
                raise ValueError(f"Row {row_number}, column {column}: invalid weight {value!r}.") from exc
            if not number.is_finite() or number < 0:
                raise ValueError(f"Row {row_number}, column {column}: weights must be finite and nonnegative.")
            numeric.append(number)
        if ore.casefold() in {"sum", "total", "totals"}:
            summary_rows.append((row_number, numeric))
            continue
        if ore.casefold() in seen_ores:
            raise ValueError(f"Row {row_number}: duplicate ore name {ore!r}.")
        seen_ores.add(ore.casefold())
        weights[ore] = {dim: number for dim, number in zip(dimensions, numeric) if number > 0}
        source_rows[ore] = row_number
        totals = [total + number for total, number in zip(totals, numeric)]

    if not weights:
        raise ValueError("No ore rows found. Export the VMWeights tab, not the lookup tab.")
    for row_number, values in summary_rows:
        for dimension, expected, actual in zip(dimensions, values, totals):
            if expected != actual:
                raise ValueError(f"Summary row {row_number}: {dimension} total is {expected}, but ore rows sum to {actual}.")
    return {
        "dimensions": dimensions,
        "weights": weights,
        "source_rows": source_rows,
        "summary_rows_skipped": [row_number for row_number, _ in summary_rows],
    }


def choose_dimensions(matrix: dict, exclusions: list[str], max_tier: int | None) -> list[str]:
    dimensions = matrix["dimensions"]
    excluded = {name for name in dimensions if is_deep_dark(name)}
    for query in exclusions:
        matches = [name for name in dimensions if name.casefold() == query.strip().casefold()
                   or base_name(name) == base_name(query)]
        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous dimension {query!r}. Use --list-dimensions for valid names.")
        excluded.add(matches[0])
    if max_tier is not None:
        excluded.update(name for name in dimensions if tier(name) > max_tier)
    return [name for name in dimensions if name not in excluded]


def make_report(matrix: dict, allowed: list[str], args: argparse.Namespace) -> dict:
    weights = matrix["weights"]
    all_ores = set(weights)
    dimension_ores = {dim: {ore for ore, sources in weights.items() if dim in sources} for dim in allowed}
    reachable = set().union(*dimension_ores.values()) if dimension_ores else set()
    unobtainable = sorted(all_ores - reachable)
    # Keep the original target intact in strict mode. Default reduction is
    # explicit in both the console and reports, never a claim of full coverage.
    target = all_ores if args.strict else reachable
    solution = solve_cover(dimension_ores, target, max_solutions=0 if args.all_solutions else 20)
    order = {dim: index for index, dim in enumerate(matrix["dimensions"])}
    if solution["feasible"]:
        solution["solutions"] = sorted(
            (sorted(cover, key=order.__getitem__) for cover in solution["solutions"]),
            key=lambda cover: tuple(order[dim] for dim in cover),
        )
        # Independently check each returned cover against the parsed weights.
        for cover in solution["solutions"]:
            actual = set().union(*(dimension_ores[dim] for dim in cover)) if cover else set()
            if not target <= actual or len(cover) != solution["minimum_count"]:
                raise RuntimeError("Solver returned an invalid coverage result.")

    source = {
        "csv_file": args.csv.name,
        "csv_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
    }
    if source["csv_sha256"] == BUNDLED_CSV_SHA256:
        source.update(url=SOURCE_URL, tab="VMWeights", range="A1:AQ321",
                      retrieved_on=SNAPSHOT_DATE, workbook_label="GTNE: 2.8.0 (v5)")
    return {
        "source": source,
        "max_rocket_tier": args.max_tier,
        "coverage_rule": "Positive raw weight means obtainable; zero or blank means absent.",
        "objective": "Minimize the number of distinct dimensions; no probability or travel-cost objective.",
        "listed_ore_count": len(all_ores),
        "obtainable_ore_count": len(reachable),
        "unobtainable_ore_count": len(unobtainable),
        "unobtainable_ores": unobtainable,
        "all_listed_ores_coverable": not unobtainable,
        "candidate_dimensions": allowed,
        "excluded_dimensions": [dim for dim in matrix["dimensions"] if dim not in allowed],
        "target_scope": "all listed ores" if args.strict or not unobtainable else "all obtainable ores only",
        "target_ore_count": len(target),
        "summary_rows_skipped": matrix["summary_rows_skipped"],
        "result": solution,
    }


def print_report(report: dict, show_all: bool) -> None:
    result = report["result"]
    print("ORE DIMENSION OPTIMIZER")
    limit = report["max_rocket_tier"]
    print("Maximum rocket tier: " + ("all (no tier limit)" if limit is None else f"T{limit}"))
    print(f"Listed ores: {report['listed_ore_count']}; obtainable with allowed dimensions: {report['obtainable_ore_count']}")
    print("Excluded: " + ", ".join(report["excluded_dimensions"]))
    if report["unobtainable_ores"]:
        print(f"\nFull coverage is IMPOSSIBLE: {report['unobtainable_ore_count']} ores have no allowed source.")
    if result["feasible"]:
        print(f"\nEXACT MINIMUM for {report['target_scope']}: {result['minimum_count']} dimensions")
        print(f"Covered target: {report['target_ore_count']} / {report['target_ore_count']} ores")
        print("\nOne optimal set:")
        for dimension in result["solutions"][0]:
            print("  - " + dimension)
        count = len(result["solutions"])
        if result["solutions_truncated"]:
            print(f"\nRetained {count} optimal covers in the result; more exist. Use --all-solutions to enumerate all.")
        else:
            print(f"\nTotal optimal covers: {count}")
        if show_all:
            print("\nAll optimal covers:")
            for index, cover in enumerate(result["solutions"], 1):
                print(f"  {index}. " + "; ".join(cover))
        elif count > 1:
            print("Use --all-solutions to print the alternative sets.")
        forced = result.get("forced_dimensions", [])
        print(f"\nDimensions forced by exclusive ores: {len(forced)}")
        for dimension in forced:
            witnesses = result["forced_by_ores"][dimension]
            print(f"  - {dimension}: {witnesses[0]}" + (f" (+{len(witnesses) - 1} others)" if len(witnesses) > 1 else ""))
    else:
        print("Strict mode: no solution covers every listed ore. No minimum is reported.")
        print("Run without --strict to minimize dimensions for all obtainable ores.")
    if report["unobtainable_ores"]:
        print("\nUnobtainable ores under these exclusions:")
        for ore in report["unobtainable_ores"]:
            print("  - " + ore)


def save_reports(prefix: Path, report: dict, matrix: dict) -> tuple[Path, Path]:
    json_path = Path(str(prefix) + ".json")
    csv_path = Path(str(prefix) + "_coverage.csv")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = report["result"]
    selected = result["solutions"][0] if result["feasible"] else []
    allowed = set(report["candidate_dimensions"])
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Ore", "Status", "Selected dimensions", "All allowed source dimensions", "Excluded source dimensions", "Source CSV row"])
        for ore, sources in matrix["weights"].items():
            covered_by = [dim for dim in selected if dim in sources]
            available = [dim for dim in sources if dim in allowed]
            excluded = [dim for dim in sources if dim not in allowed]
            status = "Covered" if covered_by else ("Unobtainable" if not available else "No cover chosen (strict run infeasible)")
            writer.writerow([ore, status, "; ".join(covered_by), "; ".join(available), "; ".join(excluded), matrix["source_rows"][ore]])
    return json_path, csv_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Input ore/dimension weight CSV (default: bundled vmweights.csv).")
    parser.add_argument("--exclude", action="append", default=[], metavar="DIMENSION", help="Also exclude this dimension; repeat as needed. Tier suffix is optional.")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS, help="Settings JSON (default: settings.json beside the program).")
    tiers = parser.add_mutually_exclusive_group()
    tiers.add_argument("--max-tier", type=parse_tier, default=argparse.SUPPRESS, metavar="N|all", help="Override the saved rocket tier for this run only.")
    tiers.add_argument("--set-tier", type=parse_tier, default=argparse.SUPPRESS, metavar="N|all", help="Save your maximum rocket tier and optimize; 'all' removes the limit.")
    tiers.add_argument("--choose-tier", action="store_true", help="Ask for and remember your rocket tier before optimizing.")
    parser.add_argument("--strict", action="store_true", help="Require all listed ores; fail explicitly if any is unobtainable.")
    parser.add_argument("--all-solutions", action="store_true", help="Enumerate and print every optimal cover (default: save up to 20, print one).")
    parser.add_argument("--report-prefix", type=Path, metavar="PATH", help="Save PATH.json and PATH_coverage.csv for this run.")
    parser.add_argument("--list-dimensions", action="store_true", help="List available dimension names and exit.")
    args = parser.parse_args(argv)
    return args


def main(argv: list[str] | None = None) -> int:
    # Windows terminals may use legacy code pages; preserve readable output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    try:
        matrix = read_matrix(args.csv)
        if args.list_dimensions:
            for dimension in matrix["dimensions"]:
                print(dimension + (" [always excluded]" if is_deep_dark(dimension) else ""))
            return 0
        apply_settings(args)
        allowed = choose_dimensions(matrix, args.exclude, args.max_tier)
        report = make_report(matrix, allowed, args)
        print_report(report, args.all_solutions)
        if args.report_prefix:
            paths = save_reports(args.report_prefix, report, matrix)
            print("\nSaved: " + ", ".join(str(path) for path in paths))
        return 0 if report["result"]["feasible"] else 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
