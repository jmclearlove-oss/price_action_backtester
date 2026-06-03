from __future__ import annotations

import argparse
from pathlib import Path
from pprint import pprint

from .config import load_config
from .data import fetch_ohlcv, load_csv, save_ohlcv_csv
from .strategy import generate_signals
from .backtest import Backtester
from .report import save_outputs, plot_backtest


def _parse_timeframes(values: list[str] | None, cfg) -> list[str]:
    if values:
        raw = []
        for value in values:
            raw.extend(part.strip() for part in value.split(','))
        timeframes = [tf for tf in raw if tf]
    else:
        timeframes = [cfg.timeframe, *cfg.higher_timeframes]
    return list(dict.fromkeys(timeframes))


def _safe_name(value: str) -> str:
    return ''.join(ch for ch in value if ch.isalnum() or ch in ('-', '_')).strip('_')


def run_backtest(args) -> None:
    cfg = load_config(args.config)
    if args.csv:
        raw = load_csv(args.csv)
    else:
        raw = fetch_ohlcv(cfg.exchange, cfg.symbol, cfg.timeframe, cfg.since, cfg.limit, cfg.proxy)

    features = generate_signals(raw, cfg)
    backtester = Backtester(cfg)
    trades, equity, metrics = backtester.run(features)

    output_dir = Path(cfg.output_dir)
    save_outputs(output_dir, trades, equity, metrics, cfg.export_trades_csv)
    features.to_csv(output_dir / 'features_signals.csv', encoding='utf-8-sig')
    if cfg.plot_enabled:
        plot_backtest(features, trades, equity, output_dir)

    print('\n=== Backtest Metrics ===')
    pprint(metrics)
    print(f'\nOutputs saved to: {output_dir.resolve()}')


def run_download(args) -> None:
    cfg = load_config(args.config)
    exchange = args.exchange or cfg.exchange
    symbol = args.symbol or cfg.symbol
    proxy = args.proxy if args.proxy is not None else cfg.proxy
    since = args.since or cfg.since
    limit = args.limit or cfg.limit
    timeframes = _parse_timeframes(args.timeframes, cfg)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print('\n=== Download OHLCV ===')
    print(f'Exchange: {exchange}')
    print(f'Symbol: {symbol}')
    print(f'Proxy: {proxy or "none"}')
    print(f'Since: {since}')
    print(f'Limit per timeframe: {limit}')
    print(f'Timeframes: {", ".join(timeframes)}')

    saved = []
    failed = []
    for timeframe in timeframes:
        print(f'\nDownloading {symbol} {timeframe} ...')
        try:
            df = fetch_ohlcv(exchange, symbol, timeframe, since, limit, proxy)
        except Exception as exc:
            failed.append((timeframe, str(exc)))
            print(f'Failed {symbol} {timeframe}: {exc}')
            continue
        filename = f'{_safe_name(exchange)}_{_safe_name(symbol)}_{_safe_name(timeframe)}.csv'
        path = output_dir / filename
        save_ohlcv_csv(df, path)
        saved.append(path)
        if df.empty:
            print(f'No rows saved: {path}')
            continue
        print(f'Saved {len(df)} rows: {path}')
        print(f'Range: {df.index.min()} -> {df.index.max()}')

    print('\nFiles saved:')
    if saved:
        for path in saved:
            print(f'- {path.resolve()}')
    else:
        print('- none')

    if failed:
        print('\nFailed timeframes:')
        for timeframe, reason in failed:
            print(f'- {timeframe}: {reason}')
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description='价格行为学交易分析与回测框架')
    sub = parser.add_subparsers(dest='command', required=True)

    bt = sub.add_parser('backtest', help='运行回测')
    bt.add_argument('--config', default='config.yaml', help='配置文件路径')
    bt.add_argument('--csv', default=None, help='本地 OHLCV CSV 路径；不传则从交易所拉取')
    bt.set_defaults(func=run_backtest)

    dl = sub.add_parser('download', help='下载交易所 OHLCV CSV 数据')
    dl.add_argument('--config', default='config.yaml', help='配置文件路径')
    dl.add_argument('--exchange', default=None, help='交易所 ID，例如 binance；默认使用配置文件')
    dl.add_argument('--symbol', default=None, help='交易对，例如 BTC/USDT；默认使用配置文件')
    dl.add_argument('--proxy', default=None, help='HTTP/HTTPS 代理，例如 http://127.0.0.1:7897；默认使用配置文件')
    dl.add_argument('--since', default=None, help='开始时间，例如 2023-01-01T00:00:00Z；默认使用配置文件')
    dl.add_argument('--limit', type=int, default=None, help='每个周期下载的 K线数量；默认使用配置文件')
    dl.add_argument('--timeframes', nargs='*', default=None, help='周期列表，例如 1m 5m 15m 1h 4h 1d；也支持逗号分隔')
    dl.add_argument('--output-dir', default='data', help='CSV 输出目录')
    dl.set_defaults(func=run_download)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
