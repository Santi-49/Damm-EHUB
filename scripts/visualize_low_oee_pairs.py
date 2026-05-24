from __future__ import annotations

from pathlib import Path

import pandas as pd

# Optional plotting libs
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing plotting libraries. Install with: pip install matplotlib seaborn"
    ) from exc

try:
    import plotly.graph_objects as go
except Exception:
    go = None

DATA_DIR = Path("/Users/nicolasvilloria/Desktop/DATOS/Damm-EHUB/data/analysis_out")
PLOTS_DIR = DATA_DIR / "plots"

PAIRS_SUMMARY = DATA_DIR / "pairs_summary.csv"
PAIRS_WORST = DATA_DIR / "pairs_worst.csv"
PAIRS_HEATMAP = DATA_DIR / "pairs_heatmap.csv"
PAIRS_SANKY = DATA_DIR / "pairs_sankey.csv"
PAIRS_CAUSES = DATA_DIR / "pairs_time_loss_causes.csv"

TOP_N = 20


def _pair_label(df: pd.DataFrame) -> pd.Series:
    return df["from_key"].astype(str) + " -> " + df["to_key"].astype(str)


def plot_worst_pairs() -> None:
    df = pd.read_csv(PAIRS_WORST)
    df = df.sort_values("mean_oee", ascending=True).head(TOP_N)
    df["pair"] = _pair_label(df)

    plt.figure(figsize=(12, 8))
    sns.barplot(data=df, x="mean_oee", y="pair", color="#2f5f8d")
    plt.title("Worst transitions by mean OEE")
    plt.xlabel("Mean OEE")
    plt.ylabel("Pair")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "worst_pairs_bar.png", dpi=200)
    plt.close()


def plot_heatmap() -> None:
    df = pd.read_csv(PAIRS_HEATMAP, index_col=0)
    if df.shape[0] > 60 or df.shape[1] > 60:
        # Keep the heatmap readable by trimming to worst pairs.
        worst = pd.read_csv(PAIRS_WORST).head(40)
        keys = sorted(set(worst["from_key"]).union(set(worst["to_key"])))
        df = df.reindex(index=keys, columns=keys)

    plt.figure(figsize=(12, 10))
    sns.heatmap(df, cmap="mako", vmin=df.min().min(), vmax=df.max().max())
    plt.title("Mean OEE by transition (heatmap)")
    plt.xlabel("To")
    plt.ylabel("From")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "pairs_heatmap.png", dpi=200)
    plt.close()


def plot_cause_breakdown() -> None:
    df = pd.read_csv(PAIRS_CAUSES)
    df["pair"] = _pair_label(df)
    worst = pd.read_csv(PAIRS_WORST).head(TOP_N)
    df = df.merge(worst[["from_key", "to_key"]], on=["from_key", "to_key"], how="inner")

    value_cols = [c for c in df.columns if c not in {"from_key", "to_key", "pair", "mean_oee", "count", "penalty"}]
    if not value_cols:
        return

    df = df.set_index("pair")[value_cols]
    df = df.fillna(0.0)

    plt.figure(figsize=(14, 8))
    df.plot(kind="barh", stacked=True, figsize=(14, 8), colormap="tab20")
    plt.title("Time-loss breakdown for worst pairs")
    plt.xlabel("Mean time (minutes or units as provided)")
    plt.ylabel("Pair")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "pairs_time_loss_breakdown.png", dpi=200)
    plt.close()


def plot_sankey() -> None:
    if go is None:
        return
    df = pd.read_csv(PAIRS_SANKY).sort_values("mean_oee", ascending=True).head(50)

    labels = pd.Index(df["from_key"].astype(str).tolist() + df["to_key"].astype(str).tolist()).unique()
    label_map = {label: idx for idx, label in enumerate(labels)}

    sources = df["from_key"].astype(str).map(label_map).tolist()
    targets = df["to_key"].astype(str).map(label_map).tolist()
    values = df["count"].tolist()

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(label=labels.tolist(), pad=10, thickness=12),
                link=dict(source=sources, target=targets, value=values),
            )
        ]
    )
    fig.update_layout(title_text="Worst transitions (by mean OEE)")
    fig.write_html(PLOTS_DIR / "pairs_sankey.html")


def main() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_worst_pairs()
    plot_heatmap()
    plot_cause_breakdown()
    plot_sankey()
    print("Plots written to:", PLOTS_DIR)


if __name__ == "__main__":
    main()
