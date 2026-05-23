"""Full ETL pipeline CLI.

Usage:
    python -m services.etl --raw data/raw --out data/clean
"""
import argparse
from pathlib import Path

from services.etl.app.implementation import _build_sync


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full LineWise ETL pipeline")
    parser.add_argument("--raw", default="data/raw", type=Path,
                        help="Directory containing raw xlsx files (default: data/raw)")
    parser.add_argument("--out", default="data/clean", type=Path,
                        help="Directory where clean CSVs are written (default: data/clean)")
    args = parser.parse_args()

    print(f"ETL: raw={args.raw} -> out={args.out}\n")
    result = _build_sync(args.raw, args.out)

    print("Tables written:")
    for table, n in result.rows_per_table.items():
        print(f"  {result.clean_dir / (table + '.csv')}  ({n} rows)")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings[:30]:
            print(f"  * {w}")
        if len(result.warnings) > 30:
            print(f"  ... ({len(result.warnings) - 30} more)")

    discarded = list(result.discarded_files)
    if discarded:
        print(f"\nDiscarded files (intentional): {discarded}")


if __name__ == "__main__":
    main()
