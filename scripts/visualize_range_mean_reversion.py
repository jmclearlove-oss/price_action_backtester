from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pa_backtester.config import load_config  # noqa: E402
from pa_backtester.range_market import add_mean_reversion_features, add_range_market_features  # noqa: E402


def to_bool(series: pd.Series) -> pd.Series:
    """Convert CSV-friendly boolean values to bool."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).ne(0)
    return series.astype(str).str.lower().isin({'true', '1', 'yes', 'y', 't'})


def load_and_prepare(csv_path: str | Path) -> pd.DataFrame:
    """Load feature CSV and add range/MR fields if they are missing."""

    df = pd.read_csv(csv_path)
    if 'timestamp' not in df.columns:
        first_col = df.columns[0]
        df = df.rename(columns={first_col: 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    required = {'close', 'last_swing_high', 'last_swing_low', 'atr'}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f'CSV missing required columns for range visualization: {missing}')

    cfg = load_config('config.yaml')
    if 'is_range_market' not in df.columns:
        df = add_range_market_features(df, cfg.range_market)
    if 'mean_reversion_long' not in df.columns:
        df = add_mean_reversion_features(df, cfg.mean_reversion)
    return df


def range_boxes(df: pd.DataFrame) -> list[dict]:
    """Build final display boxes from sequentially generated range ids."""

    if 'range_id' not in df.columns:
        return []
    boxes: list[dict] = []
    valid = df[df['range_id'].notna() & to_bool(df['is_range_market'])]
    for _, part in valid.groupby('range_id', sort=True):
        if part.empty:
            continue
        start = pd.to_datetime(part['range_start_time'].dropna().iloc[0], errors='coerce')
        if pd.isna(start):
            start = part['timestamp'].iloc[0]
        boxes.append({
            'x0': start,
            'x1': part['timestamp'].iloc[-1],
            'y0': float(part['range_low'].iloc[-1]),
            'y1': float(part['range_high'].iloc[-1]),
            'mid': float(part['range_mid'].iloc[-1]),
        })
    return boxes


def add_marker(fig, df: pd.DataFrame, column: str, label: str, symbol: str, color: str, y_offset: float = 0.0) -> None:
    """Add event markers if the column exists and has true values."""

    if column not in df.columns:
        return
    part = df[to_bool(df[column])]
    if part.empty:
        return
    fig.add_scatter(
        x=part['timestamp'],
        y=part['close'] * (1 + y_offset),
        mode='markers+text',
        name=label,
        text=[label] * len(part),
        textposition='top center' if y_offset >= 0 else 'bottom center',
        marker={'symbol': symbol, 'size': 10, 'color': color},
    )


def write_chart(df: pd.DataFrame, output: str | Path) -> bool:
    """Write the Plotly HTML chart. Return False if Plotly is unavailable."""

    try:
        import plotly.graph_objects as go
    except ImportError:
        print('Plotly is not installed; skipped range mean-reversion HTML chart.')
        return False

    boxes = range_boxes(df)
    fig = go.Figure()
    fig.add_scatter(
        x=df['timestamp'],
        y=df['close'],
        mode='lines',
        name='close',
        line={'width': 1.4, 'color': '#111827'},
    )
    if 'range_mid' in df.columns:
        fig.add_scatter(
            x=df['timestamp'],
            y=df['range_mid'],
            mode='lines',
            name='range_mid',
            line={'width': 1, 'dash': 'dot', 'color': '#64748b'},
        )

    for box in boxes:
        fig.add_shape(
            type='rect',
            x0=box['x0'],
            x1=box['x1'],
            y0=box['y0'],
            y1=box['y1'],
            fillcolor='rgba(59, 130, 246, 0.12)',
            line={'color': 'rgba(37, 99, 235, 0.35)', 'width': 1},
            layer='below',
        )
        fig.add_shape(
            type='line',
            x0=box['x0'],
            x1=box['x1'],
            y0=box['mid'],
            y1=box['mid'],
            line={'color': 'rgba(100, 116, 139, 0.45)', 'width': 1, 'dash': 'dot'},
            layer='below',
        )

    add_marker(fig, df, 'mean_reversion_long', 'MR_LONG', 'arrow-up', '#10b981', -0.001)
    add_marker(fig, df, 'mean_reversion_short', 'MR_SHORT', 'arrow-down', '#f97316', 0.001)
    add_marker(fig, df, 'mean_reversion_exit_long', 'EXIT_L', 'circle', '#059669', 0.001)
    add_marker(fig, df, 'mean_reversion_exit_short', 'EXIT_S', 'circle', '#ea580c', -0.001)
    add_marker(fig, df, 'bos_up', 'BOS_UP', 'triangle-up', '#16a34a', 0.002)
    add_marker(fig, df, 'bos_down', 'BOS_DOWN', 'triangle-down', '#dc2626', -0.002)

    start = df['timestamp'].min()
    end = df['timestamp'].max()
    mr_long_count = int(to_bool(df.get('mean_reversion_long', pd.Series(False, index=df.index))).sum())
    mr_short_count = int(to_bool(df.get('mean_reversion_short', pd.Series(False, index=df.index))).sum())
    fig.update_layout(
        title=(
            f'Range Mean Reversion | {start} -> {end} | '
            f'boxes={len(boxes)} | MR long={mr_long_count} | MR short={mr_short_count}'
        ),
        template='plotly_white',
        hovermode='x unified',
        xaxis_title='time',
        yaxis_title='close',
    )
    fig.write_html(output)
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(description='Visualize range boxes and mean-reversion signals.')
    parser.add_argument('--csv', default='outputs/features_signals.csv', help='Input features_signals.csv path')
    parser.add_argument('--output', default='outputs/range_mean_reversion.html', help='Output HTML path')
    return parser


def main() -> None:
    """CLI entrypoint."""

    args = build_parser().parse_args()
    df = load_and_prepare(args.csv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if write_chart(df, output):
        print(f'Range mean-reversion chart: {output}')


if __name__ == '__main__':
    main()
