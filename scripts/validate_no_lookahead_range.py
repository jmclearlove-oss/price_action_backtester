from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pa_backtester.config import AppConfig, load_config  # noqa: E402
from pa_backtester.range_market import add_mean_reversion_features, add_range_market_features  # noqa: E402


KEY_FIELDS = [
    'is_range_market',
    'range_high',
    'range_low',
    'range_mid',
    'mean_reversion_long',
    'mean_reversion_short',
    'mean_reversion_exit_long',
    'mean_reversion_exit_short',
]


def load_feature_csv(path: str | Path) -> pd.DataFrame:
    """Load feature CSV for no-lookahead validation."""

    df = pd.read_csv(path)
    if 'timestamp' not in df.columns:
        first_col = df.columns[0]
        df = df.rename(columns={first_col: 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    return df


def add_features(df: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    """Run range and mean-reversion features with project config."""

    out = add_range_market_features(df, cfg.range_market)
    out = add_mean_reversion_features(out, cfg.mean_reversion)
    return out


def values_equal(left: Any, right: Any) -> bool:
    """Compare scalar values while treating NaN/NA as equal."""

    if pd.isna(left) and pd.isna(right):
        return True
    if isinstance(left, (bool, int, float)) or isinstance(right, (bool, int, float)):
        try:
            return abs(float(left) - float(right)) <= 1e-12
        except (TypeError, ValueError):
            return bool(left) == bool(right)
    return left == right


def validate(df: pd.DataFrame, cfg: AppConfig) -> dict[str, Any]:
    """Compare full-batch results against one-bar-at-a-time results."""

    full_result = add_features(df, cfg)
    mismatches: list[dict[str, Any]] = []

    for i in range(len(df)):
        step_result = add_features(df.iloc[:i + 1], cfg)
        full_row = full_result.iloc[i]
        step_row = step_result.iloc[-1]
        field_mismatches = []
        for field in KEY_FIELDS:
            full_value = full_row.get(field)
            step_value = step_row.get(field)
            if not values_equal(full_value, step_value):
                field_mismatches.append({
                    'field': field,
                    'full_value': None if pd.isna(full_value) else full_value,
                    'step_value': None if pd.isna(step_value) else step_value,
                })
        if field_mismatches:
            mismatches.append({
                'row': int(i),
                'timestamp': str(full_row.get('timestamp', full_result.index[i])),
                'mismatches': field_mismatches,
            })

    return {
        'checked_rows': int(len(df)),
        'mismatch_count': int(len(mismatches)),
        'first_20_mismatches': mismatches[:20],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(description='Validate range/MR features for no-lookahead behavior.')
    parser.add_argument('--csv', default='outputs/features_signals.csv', help='Input features_signals.csv path')
    parser.add_argument('--output', default='outputs/no_lookahead_range_validation.json', help='Output JSON path')
    return parser


def main() -> None:
    """CLI entrypoint."""

    args = build_parser().parse_args()
    df = load_feature_csv(args.csv)
    cfg = load_config('config.yaml')
    report = validate(df, cfg)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'No-lookahead validation: {output}')
    print(f'checked_rows={report["checked_rows"]} mismatch_count={report["mismatch_count"]}')


if __name__ == '__main__':
    main()
