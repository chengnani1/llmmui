#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate camera-ready RQ3 figures from fixed paper statistics."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from typing import Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


TOTAL_APPS = 258
TOTAL_CHAINS = 1684

RISK_LABELS = [
    "LOW\n(Clearly Safe)",
    "MEDIUM-consistent\n(Weakly Justified)",
    "MEDIUM-over\n(Potentially Over-scoped)",
    "HIGH\n(Clearly Risky)",
]
RISK_VALUES = [7.3, 3.6, 53.1, 35.9]
RISK_COUNTS = [123, 61, 895, 605]
RISK_COLORS = ["#4C78A8", "#F2CF5B", "#F28E2B", "#E15759"]

SCENES = [
    "Album Selection & Media Upload",
    "Other",
    "Map & Location Services",
    "Content Browsing & Search",
    "Account & Identity Verification",
    "Camera, Video & QR Scanning",
    "Audio Recording & Creation",
    "Device Cleanup & System Optimization",
    "Social Interaction & Communication",
    "Network Connectivity & Device Management",
]

RISK_HEATMAP_COLUMNS = ["LOW", "MEDIUM", "HIGH"]
RISK_HEATMAP_MATRIX = np.array(
    [
        [10, 289, 3],
        [9, 145, 136],
        [16, 213, 40],
        [9, 56, 161],
        [7, 73, 103],
        [39, 103, 8],
        [7, 26, 35],
        [11, 7, 39],
        [3, 21, 16],
        [3, 7, 25],
    ],
    dtype=float,
)

SCENE_DISTRIBUTION = [
    ("Album Selection & Media Upload", 302, 17.9),
    ("Other", 290, 17.2),
    ("Map & Location Services", 269, 16.0),
    ("Content Browsing & Search", 226, 13.4),
    ("Account & Identity Verification", 183, 10.9),
    ("Camera, Video & QR Scanning", 150, 8.9),
    ("Audio Recording & Creation", 68, 4.0),
    ("Device Cleanup & System Optimization", 57, 3.4),
    ("Social Interaction & Communication", 40, 2.4),
    ("Network Connectivity & Device Management", 35, 2.1),
]

PERMISSION_DISTRIBUTION = [
    ("READ_EXTERNAL_STORAGE", 825, 22.0),
    ("WRITE_EXTERNAL_STORAGE", 825, 22.0),
    ("ACCESS_COARSE_LOCATION", 580, 15.5),
    ("ACCESS_FINE_LOCATION", 580, 15.5),
    ("READ_PHONE_NUMBERS", 257, 6.9),
    ("READ_PHONE_STATE", 257, 6.9),
    ("CAMERA", 218, 5.8),
    ("RECORD_AUDIO", 107, 2.9),
    ("READ_CONTACTS", 50, 1.3),
    ("CALL_PHONE", 33, 0.9),
    ("READ_CALL_LOG", 17, 0.4),
    ("SEND_SMS", 2, 0.1),
]
PERMISSION_BAR_COLOR = "#5B7FA3"
SCENE_BAR_COLOR = "#6F8FAF"
HIGH_RISK_BAR_COLOR = "#C95C54"
PERMISSIONS = [item[0] for item in PERMISSION_DISTRIBUTION]
PERMISSION_RISK_HEATMAP_MATRIX = np.array(
    [
        [27, 583, 215],
        [27, 583, 215],
        [22, 363, 195],
        [22, 363, 195],
        [4, 173, 80],
        [4, 173, 80],
        [13, 146, 59],
        [11, 46, 50],
        [1, 18, 31],
        [0, 14, 19],
        [0, 1, 16],
        [0, 0, 2],
    ],
    dtype=float,
)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _wrap_labels(labels: Sequence[str], width: int = 20) -> List[str]:
    return [textwrap.fill(label, width=width, break_long_words=False) for label in labels]


def _style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def draw_risk_breakdown(ax: plt.Axes, add_subfigure_label: bool = False) -> None:
    x = np.arange(len(RISK_LABELS))
    bars = ax.bar(x, RISK_VALUES, width=0.62, color=RISK_COLORS, edgecolor="black", linewidth=0.5)
    ax.set_xticks(x, RISK_LABELS)
    ax.set_ylabel("Percentage (%)")
    ax.set_ylim(0, 60)
    ax.set_title("Risk Breakdown of Permission-Context Compliance", pad=8)
    ax.yaxis.grid(True, linestyle=(0, (3, 3)), color="#D6D6D6", alpha=0.9, linewidth=0.7)
    ax.set_axisbelow(True)
    _style_axes(ax)

    for bar, pct, count in zip(bars, RISK_VALUES, RISK_COUNTS):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.0,
            f"{pct:.1f}%",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    if add_subfigure_label:
        ax.text(-0.16, 1.04, "(a)", transform=ax.transAxes, fontsize=10, fontweight="bold")


def draw_risk_breakdown_pie(ax: plt.Axes, add_subfigure_label: bool = False) -> None:
    wedges, texts, autotexts = ax.pie(
        RISK_COUNTS,
        labels=RISK_LABELS,
        colors=RISK_COLORS,
        startangle=100,
        counterclock=False,
        autopct=lambda pct: f"{pct:.1f}%",
        pctdistance=0.7,
        labeldistance=1.12,
        wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
        textprops={"fontsize": 8, "color": "#1A1A1A"},
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(8.5)
        autotext.set_weight("bold")
    ax.set_title("Risk Breakdown of Permission-Context Compliance", pad=8)
    ax.set_aspect("equal")

    if add_subfigure_label:
        ax.text(-0.12, 1.04, "(a)", transform=ax.transAxes, fontsize=10, fontweight="bold")


def draw_scene_risk_heatmap(
    ax: plt.Axes,
    add_subfigure_label: bool = False,
    show_colorbar: bool = True,
    figure: plt.Figure | None = None,
) -> None:
    wrapped_scenes = _wrap_labels(SCENES, width=22)
    im = ax.imshow(RISK_HEATMAP_MATRIX, cmap="Blues", aspect="auto")
    ax.set_xticks(np.arange(len(RISK_HEATMAP_COLUMNS)), RISK_HEATMAP_COLUMNS)
    ax.set_yticks(np.arange(len(wrapped_scenes)), wrapped_scenes)
    ax.set_title("Risk Distribution Varies across UI Task Scenarios", pad=8)
    ax.tick_params(length=0)

    max_value = float(RISK_HEATMAP_MATRIX.max())
    threshold = max_value * 0.55
    for i in range(RISK_HEATMAP_MATRIX.shape[0]):
        for j in range(RISK_HEATMAP_MATRIX.shape[1]):
            value = int(RISK_HEATMAP_MATRIX[i, j])
            ax.text(
                j,
                i,
                str(value),
                ha="center",
                va="center",
                fontsize=8,
                color="white" if value >= threshold else "#1A1A1A",
            )

    if show_colorbar and figure is not None:
        cbar = figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Number of Chains", rotation=90, labelpad=8)
        cbar.ax.tick_params(labelsize=8)

    if add_subfigure_label:
        ax.text(-0.14, 1.04, "(b)", transform=ax.transAxes, fontsize=10, fontweight="bold")


def draw_permission_distribution(ax: plt.Axes) -> None:
    labels = [item[0] for item in PERMISSION_DISTRIBUTION]
    counts = [item[1] for item in PERMISSION_DISTRIBUTION]
    percents = [item[2] for item in PERMISSION_DISTRIBUTION]
    y = np.arange(len(labels))

    bars = ax.barh(y, percents, color=PERMISSION_BAR_COLOR, edgecolor="black", linewidth=0.45, height=0.68)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Percentage of Permission Mentions (%)")
    ax.set_title("Permission Mention Distribution in RQ3", pad=8)
    ax.xaxis.grid(True, linestyle=(0, (3, 3)), color="#D6D6D6", alpha=0.9, linewidth=0.7)
    ax.set_axisbelow(True)
    _style_axes(ax)

    max_value = max(percents)
    ax.set_xlim(0, max_value + 3.5)
    for bar, count, pct in zip(bars, counts, percents):
        ax.text(
            bar.get_width() + 0.35,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}% (n={count})",
            va="center",
            ha="left",
            fontsize=8.3,
        )


def draw_permission_risk_heatmap(
    ax: plt.Axes,
    show_colorbar: bool = True,
    figure: plt.Figure | None = None,
) -> None:
    wrapped_permissions = _wrap_labels(PERMISSIONS, width=20)
    im = ax.imshow(PERMISSION_RISK_HEATMAP_MATRIX, cmap="Blues", aspect="auto")
    ax.set_xticks(np.arange(len(RISK_HEATMAP_COLUMNS)), RISK_HEATMAP_COLUMNS)
    ax.set_yticks(np.arange(len(wrapped_permissions)), wrapped_permissions)
    ax.set_title("Risk Distribution Varies across Permissions", pad=8)
    ax.tick_params(length=0)

    max_value = float(PERMISSION_RISK_HEATMAP_MATRIX.max())
    threshold = max_value * 0.55
    for i in range(PERMISSION_RISK_HEATMAP_MATRIX.shape[0]):
        for j in range(PERMISSION_RISK_HEATMAP_MATRIX.shape[1]):
            value = int(PERMISSION_RISK_HEATMAP_MATRIX[i, j])
            ax.text(
                j,
                i,
                str(value),
                ha="center",
                va="center",
                fontsize=8,
                color="white" if value >= threshold else "#1A1A1A",
            )

    if show_colorbar and figure is not None:
        cbar = figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Number of Chains", rotation=90, labelpad=8)
        cbar.ax.tick_params(labelsize=8)


def draw_scene_distribution(ax: plt.Axes) -> None:
    labels = [item[0] for item in SCENE_DISTRIBUTION]
    counts = [item[1] for item in SCENE_DISTRIBUTION]
    percents = [item[2] for item in SCENE_DISTRIBUTION]
    y = np.arange(len(labels))

    bars = ax.barh(y, percents, color=SCENE_BAR_COLOR, edgecolor="black", linewidth=0.45, height=0.68)
    ax.set_yticks(y, _wrap_labels(labels, width=28))
    ax.invert_yaxis()
    ax.set_xlabel("Percentage of Chains (%)")
    ax.set_title("Scenario Distribution in RQ3", pad=8)
    ax.xaxis.grid(True, linestyle=(0, (3, 3)), color="#D6D6D6", alpha=0.9, linewidth=0.7)
    ax.set_axisbelow(True)
    _style_axes(ax)

    max_value = max(percents)
    ax.set_xlim(0, max_value + 3.5)
    for bar, count, pct in zip(bars, counts, percents):
        ax.text(
            bar.get_width() + 0.35,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}% (n={count})",
            va="center",
            ha="left",
            fontsize=8.3,
        )


def draw_high_risk_ratio_by_scene(ax: plt.Axes) -> None:
    totals = RISK_HEATMAP_MATRIX.sum(axis=1)
    high_counts = RISK_HEATMAP_MATRIX[:, 2]
    ratios = (high_counts / totals) * 100.0

    ranked = sorted(
        zip(SCENES, high_counts.astype(int), totals.astype(int), ratios),
        key=lambda item: (-item[3], item[0]),
    )
    labels = [item[0] for item in ranked]
    high_values = [item[1] for item in ranked]
    total_values = [item[2] for item in ranked]
    ratio_values = [item[3] for item in ranked]
    y = np.arange(len(labels))

    bars = ax.barh(
        y,
        ratio_values,
        color=HIGH_RISK_BAR_COLOR,
        edgecolor="black",
        linewidth=0.45,
        height=0.68,
    )
    ax.set_yticks(y, _wrap_labels(labels, width=28))
    ax.invert_yaxis()
    ax.set_xlabel("High-risk Ratio within Scenario (%)")
    ax.set_title("High-risk Ratio by UI Task Scenario", pad=8)
    ax.xaxis.grid(True, linestyle=(0, (3, 3)), color="#D6D6D6", alpha=0.9, linewidth=0.7)
    ax.set_axisbelow(True)
    _style_axes(ax)

    max_value = max(ratio_values)
    ax.set_xlim(0, max_value + 9)
    for bar, high_count, total_count, ratio in zip(bars, high_values, total_values, ratio_values):
        ax.text(
            bar.get_width() + 0.45,
            bar.get_y() + bar.get_height() / 2,
            f"{ratio:.1f}% ({high_count}/{total_count})",
            va="center",
            ha="left",
            fontsize=8.3,
        )


def save_figure(fig: plt.Figure, png_path: Path, pdf_path: Path) -> None:
    fig.savefig(png_path, dpi=400, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)


def make_figure_a(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    draw_risk_breakdown(ax)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_final_risk_breakdown_bar.png",
        output_dir / "rq3_final_risk_breakdown_bar.pdf",
    )


def make_figure_b(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    draw_scene_risk_heatmap(ax, figure=fig)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_scene_risk_heatmap_final.png",
        output_dir / "rq3_scene_risk_heatmap_final.pdf",
    )


def make_figure_ab(output_dir: Path) -> None:
    fig = plt.figure(figsize=(12.2, 4.6), facecolor="white", constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.34)

    ax_left = fig.add_subplot(gs[0, 0])
    ax_right = fig.add_subplot(gs[0, 1])

    draw_risk_breakdown(ax_left, add_subfigure_label=True)
    draw_scene_risk_heatmap(ax_right, add_subfigure_label=True, figure=fig)

    save_figure(
        fig,
        output_dir / "rq3_rq3_ab_figure.png",
        output_dir / "rq3_rq3_ab_figure.pdf",
    )


def make_clean_ab_figure(output_dir: Path) -> None:
    fig = plt.figure(figsize=(10, 4.5), facecolor="white", constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.28)

    ax_left = fig.add_subplot(gs[0, 0])
    ax_right = fig.add_subplot(gs[0, 1])

    draw_risk_breakdown_pie(ax_left, add_subfigure_label=True)
    draw_scene_risk_heatmap(ax_right, add_subfigure_label=True, figure=fig)

    save_figure(
        fig,
        output_dir / "rq3_final_ab_clean.png",
        output_dir / "rq3_final_ab_clean.pdf",
    )


def make_permission_figure(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.9), facecolor="white")
    draw_permission_distribution(ax)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_permission_distribution_clean.png",
        output_dir / "rq3_permission_distribution_clean.pdf",
    )


def make_permission_risk_heatmap(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 5.4), facecolor="white")
    draw_permission_risk_heatmap(ax, figure=fig)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_permission_risk_heatmap_final.png",
        output_dir / "rq3_permission_risk_heatmap_final.pdf",
    )


def make_scene_figure(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.0), facecolor="white")
    draw_scene_distribution(ax)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_scene_distribution_clean.png",
        output_dir / "rq3_scene_distribution_clean.pdf",
    )


def make_high_risk_ratio_figure(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.8, 5.0), facecolor="white")
    draw_high_risk_ratio_by_scene(ax)
    fig.tight_layout()
    save_figure(
        fig,
        output_dir / "rq3_high_risk_ratio_by_scene.png",
        output_dir / "rq3_high_risk_ratio_by_scene.pdf",
    )


def write_markdown_note(output_dir: Path) -> None:
    note = "\n".join(
        [
            "# RQ3 Camera-Ready Figures",
            "",
            "## Figure A",
            "- File: `rq3_final_risk_breakdown_bar.png` / `rq3_final_risk_breakdown_bar.pdf`",
            "- Meaning: This figure shows the final paper-ready risk breakdown over 1,684 permission-centric interaction chains. It highlights that clearly safe chains are rare, while `MEDIUM-over` dominates the dataset.",
            "- Recommended LaTeX caption: `Risk breakdown of permission-centric interaction chains in RQ3. Clearly safe cases are rare, while medium-risk cases are overwhelmingly dominated by over-scoped permission usage.`",
            "- Recommended reference: `Figure 8(a)`",
            "",
            "## Figure B",
            "- File: `rq3_scene_risk_heatmap_final.png` / `rq3_scene_risk_heatmap_final.pdf`",
            "- Meaning: This heatmap shows how risk levels distribute across UI task scenarios, emphasizing that risk is strongly scene-dependent rather than uniform across app contexts.",
            "- Recommended LaTeX caption: `Risk distribution across UI task scenarios. Medium- and high-risk permission requests are concentrated in specific scenarios, showing that permission risk is strongly tied to UI context.`",
            "- Recommended reference: `Figure 8(b)`",
            "",
            "## Figure AB",
            "- File: `rq3_rq3_ab_figure.png` / `rq3_rq3_ab_figure.pdf`",
            "- Meaning: This combined figure places the global risk breakdown and the scene-conditioned heatmap side by side, suitable for the main RQ3 result figure in the paper.",
            "- Recommended LaTeX caption: `RQ3 results on real-world permission-centric interaction chains. (a) Clearly safe chains account for only a small fraction of the dataset, while medium-risk cases are largely driven by over-scoped permission usage. (b) Risk levels vary substantially across UI task scenarios, indicating strong scene dependence.`",
            "- Recommended reference: `Figure 8`, with sub-references `Figure 8(a)` and `Figure 8(b)`",
            "",
            "## Appendix Suggestions",
            "- File: `rq3_scene_distribution_clean.png` / `rq3_scene_distribution_clean.pdf`",
            "- Meaning: This appendix-style figure shows the distribution of UI task scenarios in the RQ3 dataset, making the scenario composition visible without distracting from the main findings.",
            "- Suggested use: supplementary or appendix figure rather than a main-result figure.",
            "- File: `rq3_permission_distribution_clean.png` / `rq3_permission_distribution_clean.pdf`",
            "- Meaning: This appendix-style figure shows the distribution of permission mentions, highlighting that storage and location permissions dominate the observed request population.",
            "- Suggested use: supplementary or appendix figure rather than a main-result figure.",
            "- File: `rq3_permission_risk_heatmap_final.png` / `rq3_permission_risk_heatmap_final.pdf`",
            "- Meaning: This companion heatmap shows that risk distribution also varies substantially across permission types, complementing the scenario-based heatmap.",
            "- Suggested use: supplementary or appendix figure when discussing which permission families are most associated with medium- and high-risk requests.",
            "- File: `rq3_high_risk_ratio_by_scene.png` / `rq3_high_risk_ratio_by_scene.pdf`",
            "- Meaning: This supplementary bar chart ranks UI task scenarios by the fraction of chains labeled as high risk, making the most risk-concentrated scenarios immediately visible.",
            "- Suggested use: appendix figure when you want to emphasize which scenarios most strongly concentrate clearly risky chains.",
            "- Scene distribution is kept as a horizontal bar chart ordered by chain count.",
            "- Permission distribution is kept as a Top-N horizontal bar chart over permission mentions.",
            "",
            "## Fixed Input Data",
            f"- Total apps: {TOTAL_APPS}",
            f"- Total chains: {TOTAL_CHAINS}",
        ]
    )
    (output_dir / "rq3_camera_ready_notes.md").write_text(note + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate camera-ready ASE/ICSE-style RQ3 figures.")
    parser.add_argument(
        "--output-dir",
        default="/Volumes/Charon/data/code/llm_ui/code/data/rq3/processed/rq3_visualizations",
        help="directory to save figure outputs",
    )
    args = parser.parse_args()

    configure_style()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    make_figure_a(output_dir)
    make_figure_b(output_dir)
    make_figure_ab(output_dir)
    make_clean_ab_figure(output_dir)
    make_permission_figure(output_dir)
    make_permission_risk_heatmap(output_dir)
    make_scene_figure(output_dir)
    make_high_risk_ratio_figure(output_dir)
    write_markdown_note(output_dir)

    print(f"[DONE] output_dir={output_dir}")
    print("[DONE] files=")
    for name in [
        "rq3_final_risk_breakdown_bar.png",
        "rq3_final_risk_breakdown_bar.pdf",
        "rq3_scene_risk_heatmap_final.png",
        "rq3_scene_risk_heatmap_final.pdf",
        "rq3_rq3_ab_figure.png",
        "rq3_rq3_ab_figure.pdf",
        "rq3_final_ab_clean.png",
        "rq3_final_ab_clean.pdf",
        "rq3_permission_distribution_clean.png",
        "rq3_permission_distribution_clean.pdf",
        "rq3_permission_risk_heatmap_final.png",
        "rq3_permission_risk_heatmap_final.pdf",
        "rq3_scene_distribution_clean.png",
        "rq3_scene_distribution_clean.pdf",
        "rq3_high_risk_ratio_by_scene.png",
        "rq3_high_risk_ratio_by_scene.pdf",
        "rq3_camera_ready_notes.md",
    ]:
        print(name)


if __name__ == "__main__":
    main()
