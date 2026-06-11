from __future__ import annotations

import argparse
import json
import math
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


def event_direction(event: str) -> tuple[str, int]:
    """Return the semantic direction label and multiplier for an event."""

    if event in SHORT_DIRECTION_EVENTS:
        return 'SHORT', -1
    return 'LONG', 1


def profit_factor(strategy_returns: pd.Series) -> float | None:
    """Calculate gross profit divided by absolute gross loss."""

    gross_profit = float(strategy_returns[strategy_returns > 0].sum())
    gross_loss = float(strategy_returns[strategy_returns < 0].abs().sum())
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def build_stats_row(event: str, horizon: int, direction_label: str, price_returns: pd.Series, direction: int) -> dict[str, Any]:
    """Build one event/horizon statistics row from raw price returns."""

    count = int(price_returns.count())
    base = {
        'event': event,
        'horizon': horizon,
        'direction': direction_label,
        'count': count,
    }
    if count == 0:
        return {
            **base,
            'mean_return': None,
            'median_return': None,
            'mean_price_return': None,
            'median_price_return': None,
            'mean_strategy_return': None,
            'median_strategy_return': None,
            'win_rate': None,
            'avg_win': None,
            'avg_loss': None,
            'profit_factor': None,
            'expectancy': None,
            'edge_score': None,
            'max_return': None,
            'min_return': None,
        }

    strategy_returns = price_returns * direction
    wins = strategy_returns[strategy_returns > 0]
    losses = strategy_returns[strategy_returns < 0]
    win_rate = float(strategy_returns.gt(0).mean())
    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.abs().mean()) if not losses.empty else 0.0
    mean_strategy_return = float(strategy_returns.mean())
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    edge_score = mean_strategy_return * win_rate * math.log1p(count)

    return {
        **base,
        'mean_return': float(price_returns.mean()),
        'median_return': float(price_returns.median()),
        'mean_price_return': float(price_returns.mean()),
        'median_price_return': float(price_returns.median()),
        'mean_strategy_return': mean_strategy_return,
        'median_strategy_return': float(strategy_returns.median()),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor(strategy_returns),
        'expectancy': float(expectancy),
        'edge_score': float(edge_score),
        'max_return': float(price_returns.max()),
        'min_return': float(price_returns.min()),
    }


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

        direction_label, direction = event_direction(event)

        for horizon in horizons:
            future_return = df['close'].shift(-horizon) / df['close'] - 1
            price_returns = future_return[event_mask].dropna()
            rows.append(build_stats_row(event, horizon, direction_label, price_returns, direction))

    results = pd.DataFrame(rows, columns=[
        'event',
        'horizon',
        'direction',
        'count',
        'mean_return',
        'median_return',
        'mean_price_return',
        'median_price_return',
        'mean_strategy_return',
        'median_strategy_return',
        'win_rate',
        'avg_win',
        'avg_loss',
        'profit_factor',
        'expectancy',
        'edge_score',
        'max_return',
        'min_return',
    ])

    summary = {
        'rows': int(len(df)),
        'events': events,
        'horizons': horizons,
        'metrics': results.columns.tolist(),
        'direction_rules': {
            'LONG': sorted(LONG_DIRECTION_EVENTS),
            'SHORT': sorted(SHORT_DIRECTION_EVENTS),
        },
        'return_definitions': {
            'price_return': 'close.shift(-horizon) / close - 1',
            'strategy_return': 'price_return * direction, where LONG=+1 and SHORT=-1',
            'win_rate': 'share of strategy_return values greater than 0',
            'edge_score': 'mean_strategy_return * win_rate * log1p(count)',
        },
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
            'best_by_edge_score': event_rows.sort_values('edge_score', ascending=False, na_position='last').head(1).to_dict('records'),
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
        'results': json.loads(results.to_json(orient='records')),
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
    """Write grouped bar charts for strategy-return edge metrics."""

    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    chart_df = results.copy()
    metrics = [
        ('mean_strategy_return', 'Mean Strategy Return'),
        ('expectancy', 'Expectancy'),
        ('edge_score', 'Edge Score'),
    ]
    for metric, _ in metrics:
        chart_df[metric] = pd.to_numeric(chart_df[metric], errors='coerce')

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[title for _, title in metrics],
    )
    horizons = sorted(chart_df['horizon'].dropna().unique())
    colors = ['#2563eb', '#16a34a', '#f97316', '#9333ea', '#dc2626', '#0891b2']

    for row, (metric, _) in enumerate(metrics, start=1):
        for idx, horizon in enumerate(horizons):
            part = chart_df[chart_df['horizon'] == horizon]
            fig.add_trace(
                go.Bar(
                    x=part['event'],
                    y=part[metric],
                    name=f'{horizon}',
                    marker_color=colors[idx % len(colors)],
                    legendgroup=str(horizon),
                    showlegend=row == 1,
                ),
                row=row,
                col=1,
            )

    fig.update_layout(
        title='Event Study: Direction-Adjusted Signal Edge',
        template='plotly_white',
        barmode='group',
        legend_title_text='horizon',
        height=900,
    )
    fig.update_yaxes(tickformat='.2%', row=1, col=1)
    fig.update_yaxes(tickformat='.2%', row=2, col=1)
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
