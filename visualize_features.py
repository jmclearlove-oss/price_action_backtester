import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def to_bool(s):
    return s.astype(str).str.lower().isin(["true", "1", "yes"])


def add_event_markers(fig, df, col, name, y_col, symbol, color, row=1):
    if col not in df.columns:
        return

    mask = to_bool(df[col])
    event_df = df[mask].copy()

    if event_df.empty:
        return

    fig.add_trace(
        go.Scatter(
            x=event_df["timestamp"],
            y=event_df[y_col],
            mode="markers+text",
            name=name,
            text=[name] * len(event_df),
            textposition="top center",
            marker=dict(size=11, symbol=symbol, color=color),
        ),
        row=row,
        col=1,
    )


def add_swing_markers(fig, df):
    if "swing_label" not in df.columns:
        return

    label_colors = {
        "HH": "#22c55e",
        "HL": "#3b82f6",
        "LH": "#f97316",
        "LL": "#ef4444",
        "H": "#94a3b8",
        "L": "#94a3b8",
    }

    for label, color in label_colors.items():
        part = df[df["swing_label"] == label].copy()
        if part.empty:
            continue

        if label in ["HH", "LH", "H"]:
            y = part["swing_high_price"].fillna(part["close"])
            position = "top center"
            symbol = "triangle-down"
        else:
            y = part["swing_low_price"].fillna(part["close"])
            position = "bottom center"
            symbol = "triangle-up"

        fig.add_trace(
            go.Scatter(
                x=part["timestamp"],
                y=y,
                mode="markers+text",
                name=label,
                text=[label] * len(part),
                textposition=position,
                marker=dict(size=12, symbol=symbol, color=color),
            ),
            row=1,
            col=1,
        )


def add_trend_state(fig, df):
    if "trend_state" not in df.columns:
        return

    mapping = {
        "DOWNTREND": -1,
        "RANGE": 0,
        "UPTREND": 1,
    }

    trend = df["trend_state"].fillna("RANGE").map(mapping).fillna(0)

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=trend,
            mode="lines",
            name="trend_state",
            line=dict(width=2, color="#64748b"),
        ),
        row=2,
        col=1,
    )


def add_signal_panel(fig, df):
    cols = {
        "long_signal": 1,
        "short_signal": -1,
        "bos_up": 0.6,
        "bos_down": -0.6,
        "choch_up": 0.3,
        "choch_down": -0.3,
    }

    colors = {
        "long_signal": "#22c55e",
        "short_signal": "#ef4444",
        "bos_up": "#16a34a",
        "bos_down": "#dc2626",
        "choch_up": "#0ea5e9",
        "choch_down": "#f97316",
    }

    for col, y_value in cols.items():
        if col not in df.columns:
            continue

        mask = to_bool(df[col])
        part = df[mask].copy()

        if part.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=part["timestamp"],
                y=[y_value] * len(part),
                mode="markers",
                name=col,
                marker=dict(size=8, color=colors[col]),
            ),
            row=3,
            col=1,
        )


def build_stats(df):
    stats = {}

    for col in ["bos_up", "bos_down", "choch_up", "choch_down", "long_signal", "short_signal"]:
        if col in df.columns:
            stats[col] = int(to_bool(df[col]).sum())

    if "swing_label" in df.columns:
        for label in ["HH", "HL", "LH", "LL", "H", "L"]:
            stats[label] = int((df["swing_label"] == label).sum())

    return stats


def visualize(csv_path):
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    required = {"timestamp", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.68, 0.16, 0.16],
        subplot_titles=[
            "Close line + market structure",
            "Trend state: UPTREND=1, RANGE=0, DOWNTREND=-1",
            "Structure events and trading signals",
        ],
    )

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["close"],
            mode="lines",
            name="close",
            line=dict(width=1.5, color="#111827"),
        ),
        row=1,
        col=1,
    )

    if "last_swing_high" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["last_swing_high"],
                mode="lines",
                name="last_swing_high",
                line=dict(width=1, dash="dot", color="#16a34a"),
            ),
            row=1,
            col=1,
        )

    if "last_swing_low" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["last_swing_low"],
                mode="lines",
                name="last_swing_low",
                line=dict(width=1, dash="dot", color="#dc2626"),
            ),
            row=1,
            col=1,
        )

    add_swing_markers(fig, df)

    add_event_markers(fig, df, "bos_up", "BOS_UP", "close", "arrow-up", "#16a34a")
    add_event_markers(fig, df, "bos_down", "BOS_DOWN", "close", "arrow-down", "#dc2626")
    add_event_markers(fig, df, "choch_up", "CHOCH_UP", "close", "diamond", "#0ea5e9")
    add_event_markers(fig, df, "choch_down", "CHOCH_DOWN", "close", "diamond", "#f97316")

    add_trend_state(fig, df)
    add_signal_panel(fig, df)

    stats = build_stats(df)
    stats_text = "<br>".join([f"{k}: {v}" for k, v in stats.items()])

    fig.add_annotation(
        text=stats_text,
        align="left",
        showarrow=False,
        xref="paper",
        yref="paper",
        x=1.01,
        y=0.98,
        bordercolor="#cbd5e1",
        borderwidth=1,
        bgcolor="#ffffff",
        font=dict(size=12),
    )

    fig.update_layout(
        title=f"Market Structure Debug View - {csv_path.name}",
        height=950,
        width=1500,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=220, t=90, b=50),
    )

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Trend", row=2, col=1)
    fig.update_yaxes(title_text="Signal", row=3, col=1)

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "market_structure_line.html"
    fig.write_html(output_path, include_plotlyjs="cdn")

    print(f"Saved to: {output_path.resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_features.py outputs/features_signals.csv")
        sys.exit(1)

    visualize(sys.argv[1])