from __future__ import annotations

from pathlib import Path
import json
import pandas as pd


def save_outputs(output_dir: str | Path, trades: pd.DataFrame, equity: pd.DataFrame, metrics: dict, export_trades_csv: bool = True) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if export_trades_csv:
        trades.to_csv(out / 'trades.csv', index=False, encoding='utf-8-sig')
    equity.to_csv(out / 'equity_curve.csv', encoding='utf-8-sig')
    with open(out / 'metrics.json', 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def plot_backtest(df: pd.DataFrame, trades: pd.DataFrame, equity: pd.DataFrame, output_dir: str | Path) -> None:
    import matplotlib.pyplot as plt

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df.index, df['close'], label='close')
    if 'ema_fast' in df:
        ax.plot(df.index, df['ema_fast'], label='ema_fast')
    if 'ema_slow' in df:
        ax.plot(df.index, df['ema_slow'], label='ema_slow')
    if not trades.empty:
        for _, t in trades.iterrows():
            et = pd.to_datetime(t['entry_time'])
            xt = pd.to_datetime(t['exit_time'])
            marker = '^' if t['side'] == 'long' else 'v'
            ax.scatter(et, t['entry_price'], marker=marker, s=60)
            ax.scatter(xt, t['exit_price'], marker='x', s=50)
    ax.set_title('Price Action Backtest')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'price_signals.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(equity.index, equity['equity'], label='equity')
    ax.set_title('Equity Curve')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'equity_curve.png', dpi=150)
    plt.close(fig)
