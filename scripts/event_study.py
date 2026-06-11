from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


EVENT_COLUMNS = [
    'bos_up',
    'bos_down',
    'choch_up',
    'choch_down',
    'long_signal',
    'short_signal',
]
LONG_DIRECTION_EVENTS = {'bos_up', 'choch_up', 'long_signal'}
SHORT_DIRECTION_EVENTS = {'bos_down', 'choch_down', 'short_signal'}
DEFAULT_HORIZONS = [5, 10, 20, 50]


def parse_bool_series(series: pd.Series) -> pd.Series:
    """Convert common CSV boolean representations to a boolean Series."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).ne(0)
    return series.astype(str).str.lower().isin({'true', '1', 'yes', 'y', 't'})


def load_features_csv(path: str | Path) -> pd.DataFrame:
    """Load a features/signals CSV and validate the minimal required columns."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f'CSV not found: {csv_path}')

    df = pd.read_csv(csv_path)
    required = {'close'}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f'CSV missing required columns: {missing}')

    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    return df


def calculate_event_stats(
    df: pd.DataFrame,
    events: list[str] | None = None,
    horizons: list[int] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calculate forward-return statistics for each event and horizon."""

    events = events or EVENT_COLUMNS
    horizons = horizons or DEFAULT_HORIZONS
    horizons = [int(h) for h in horizons if int(h) > 0]
    rows: list[dict[str, Any]] = []
    missing_event_columns: list[str] = []
    empty_events: list[str] = []

    for event in events:
        if event in df.columns:
            event_mask = parse_bool_series(df[event])
        else:
            event_mask = pd.Series(False, index=df.index)
            missing_event_columns.append(event)

        if int(event_mask.sum()) == 0:
            empty_events.append(event)

        is_long_direction = event in LONG_DIRECTION_EVENTS
        is_short_direction = event in SHORT_DIRECTION_EVENTS

        for horizon in horizons:
            future_return = df['close'].shift(-horizon) / df['close'] - 1
            event_returns = future_return[event_mask].dropna()
            count = int(event_returns.count())

            if count:
                if is_long_direction:
                    wins = event_returns.gt(0)
                elif is_short_direction:
                    wins = event_returns.lt(0)
                else:
                    wins = pd.Series(False, index=event_returns.index)

                rows.append({
                    'event': event,
                    'horizon': horizon,
                    'count': count,
                    'mean_return': float(event_returns.mean()),
                    'median_return': float(event_returns.median()),
                    'win_rate': float(wins.mean()),
                    'max_return': float(event_returns.max()),
                    'min_return': float(event_returns.min()),
                })
            else:
                rows.append({
                    'event': event,
                    'horizon': horizon,
                    'count': 0,
                    'mean_return': None,
                    'median_return': None,
                    'win_rate': None,
                    'max_return': None,
                    'min_return': None,
                })

    results = pd.DataFrame(rows, columns=[
        'event',
        'horizon',
        'count',
        'mean_return',
        'median_return',
        'win_rate',
        'max_return',
        'min_return',
    ])

    summary = {
        'rows': int(len(df)),
        'events': events,
        'horizons': horizons,
        'missing_event_columns': missing_event_columns,
        'empty_events': sorted(set(empty_events)),
        'data_warnings': [],
    }
    if len(df) <= max(horizons, default=0):
        summary['data_warnings'].append('Not enough rows for the largest horizon; some counts may be 0.')

    by_event: dict[str, dict[str, Any]] = {}
    for event in events:
        event_rows = results[results['event'] == event]
        by_event[event] = {
            'total_valid_forward_returns': int(event_rows['count'].sum()),
            'horizons_with_data': event_rows.loc[event_rows['count'] > 0, 'horizon'].astype(int).tolist(),
        }
    summary['by_event'] = by_event
    return results, summary


def write_outputs(
    results: pd.DataFrame,
    summary: dict[str, Any],
    output_dir: str | Path,
    source_csv: str | Path,
) -> dict[str, Path | None]:
    """Write CSV, JSON, and optionally a Plotly HTML chart."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / 'event_study.csv'
    json_path = out_dir / 'event_study_summary.json'
    html_path = out_dir / 'event_study.html'

    results.to_csv(csv_path, index=False, encoding='utf-8-sig')

    payload = {
        **summary,
        'source_csv': str(source_csv),
        'outputs': {
            'csv': str(csv_path),
            'json': str(json_path),
            'html': str(html_path),
        },
    }

    try:
        write_event_study_chart(results, html_path)
        payload['plotly_available'] = True
    except ImportError:
        payload['plotly_available'] = False
        payload['outputs']['html'] = None

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'csv': csv_path, 'json': json_path, 'html': html_path if payload['plotly_available'] else None}


def write_event_study_chart(results: pd.DataFrame, html_path: Path) -> None:
    """Write a grouped bar chart of mean returns by event and horizon."""

    import plotly.express as px

    chart_df = results.copy()
    chart_df['mean_return'] = pd.to_numeric(chart_df['mean_return'], errors='coerce')
    fig = px.bar(
        chart_df,
        x='event',
        y='mean_return',
        color=chart_df['horizon'].astype(str),
        barmode='group',
        labels={'color': 'horizon', 'mean_return': 'mean_return'},
        title='Event Study: Mean Forward Return by Event and Horizon',
    )
    fig.update_layout(template='plotly_white', yaxis_tickformat='.2%')
    fig.write_html(html_path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""

    parser = argparse.ArgumentParser(description='Run BOS / CHOCH / signal event study.')
    parser.add_argument('--csv', default='outputs/features_signals.csv', help='Input features_signals.csv path')
    parser.add_argument('--horizons', nargs='+', type=int, default=DEFAULT_HORIZONS, help='Forward horizons in bars')
    parser.add_argument('--output-dir', default='outputs', help='Directory for event study outputs')
    return parser


def main() -> None:
    """CLI entrypoint."""

    args = build_parser().parse_args()
    df = load_features_csv(args.csv)
    results, summary = calculate_event_stats(df, horizons=args.horizons)
    paths = write_outputs(results, summary, args.output_dir, args.csv)

    print(f'Event study CSV: {paths["csv"]}')
    print(f'Event study summary: {paths["json"]}')
    if paths['html'] is not None:
        print(f'Event study chart: {paths["html"]}')
    else:
        print('Plotly is not installed; skipped HTML chart.')


if __name__ == '__main__':
    main()
