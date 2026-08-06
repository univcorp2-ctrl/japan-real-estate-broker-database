from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .quality import audit_rows
from .validate import load_rows, validate_rows

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "real_estate_brokers.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "data-quality.json"


def run_quality_gate(
    input_path: Path,
    output_path: Path,
    *,
    strict_legacy: bool = False,
) -> tuple[int, int]:
    rows = load_rows(input_path)
    validation_errors = validate_rows(rows)
    issues = audit_rows(rows, strict_legacy=strict_legacy)
    error_count = len(validation_errors) + sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "input": str(input_path),
                "row_count": len(rows),
                "strict_legacy": strict_legacy,
                "error_count": error_count,
                "warning_count": warning_count,
                "validation_errors": validation_errors,
                "issues": [asdict(issue) for issue in issues],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return error_count, warning_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit broker contact data quality")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict-legacy", action="store_true")
    args = parser.parse_args()
    errors, warnings = run_quality_gate(
        args.input,
        args.output,
        strict_legacy=args.strict_legacy,
    )
    print(f"data-quality errors={errors} warnings={warnings} report={args.output}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
