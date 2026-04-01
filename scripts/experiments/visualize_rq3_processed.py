#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build reusable RQ3 visualizations from a processed phase3 dataset."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager


FINAL_DECISION_ORDER = ["CLEARLY_OK", "NEED_REVIEW", "CLEARLY_RISKY"]
FINAL_RISK_ORDER = ["LOW", "MEDIUM", "HIGH"]
DERIVED_RISK_ORDER = ["LOW", "MEDIUM-consistent", "MEDIUM-over", "HIGH"]
REASON_ORDER = ["overreach", "weak_necessity", "inconsistency"]
TOP_N_SCENES = 10
TOP_N_PERMISSIONS = 12
TOP_N_APPS = 15

DECISION_COLORS = {
    "CLEARLY_OK": "#2E8B57",
    "NEED_REVIEW": "#E0A106",
    "CLEARLY_RISKY": "#B03A2E",
}

RISK_COLORS = {
    "LOW": "#3E8EDE",
    "MEDIUM": "#D98E04",
    "HIGH": "#A61B1B",
}

DERIVED_RISK_COLORS = {
    "LOW": "#3E8EDE",
    "MEDIUM-consistent": "#77AADD",
    "MEDIUM-over": "#D98E04",
    "HIGH": "#A61B1B",
}

SCENE_COLOR = "#4C6A92"
PERMISSION_COLOR = "#7A5C61"
APP_COLOR = "#4B8F8C"
HIST_COLOR = "#A8B8CC"
REASON_COLORS = {
    "overreach": "#D98E04",
    "weak_necessity": "#4C78A8",
    "inconsistency": "#B03A2E",
}
REASON_LABELS = {
    "overreach": "Overreach",
    "weak_necessity": "Weak Necessity",
    "inconsistency": "Inconsistency",
}

UI_SCENE_LABEL_EN = {
    "账号与身份认证": "Account & Identity Verification",
    "地图与位置服务": "Map & Location Services",
    "内容浏览与搜索": "Content Browsing & Search",
    "社交互动与通信": "Social Interaction & Communication",
    "音频录制与创作": "Audio Recording & Creation",
    "图像视频拍摄与扫码": "Camera, Video & QR Scanning",
    "相册选择与媒体上传": "Album Selection & Media Upload",
    "商品浏览与消费": "Product Browsing & Shopping",
    "支付与金融交易": "Payment & Financial Transactions",
    "文件与数据管理": "File & Data Management",
    "设备清理与系统优化": "Device Cleanup & System Optimization",
    "网络连接与设备管理": "Network Connectivity & Device Management",
    "用户反馈与客服": "User Feedback & Customer Support",
    "其他": "Other",
    "未知场景": "Unknown",
}


def _configure_fonts() -> None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font_name in ["Arial Unicode MS", "PingFang SC", "STHeiti", "Songti SC", "Noto Sans CJK SC", "SimHei"]:
        if font_name in available:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


_configure_fonts()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _iter_app_dirs(processed_root: Path) -> Iterable[Path]:
    for child in sorted(processed_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("._") or child.name.startswith("_archive"):
            continue
        if not any((child / filename).exists() for filename in ("result.json", "result_permission.json", "result_semantic_v2.json", "result_llm_review.json", "result_final_decision.json")):
            if not any(child.glob("chain_*.png")):
                continue
        yield child


def _safe_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _format_label(label: str) -> str:
    return label.replace("_", "\n")


def _scene_label_en(label: str) -> str:
    return UI_SCENE_LABEL_EN.get(label, label or "Unknown")


def _derive_medium_bucket(row: Dict[str, Any]) -> Tuple[str, str]:
    risk = str(row.get("final_risk", "") or "").strip() or "UNKNOWN"
    necessity = str((row.get("necessity") or {}).get("label", "") or "unknown")
    consistency = str((row.get("consistency") or {}).get("label", "") or "unknown")
    over_scope = str((row.get("over_scope") or {}).get("label", "") or "unknown")

    if risk == "LOW":
        return "LOW", "direct_final_risk_low"
    if risk == "HIGH":
        return "HIGH", "direct_final_risk_high"
    if risk != "MEDIUM":
        return risk, "unknown"

    if over_scope in {"potentially_over_scoped", "over_scoped"}:
        return "MEDIUM-over", "medium_with_overreach"
    if over_scope == "minimal":
        if consistency in {"consistent", "weakly_consistent"} and necessity in {"helpful", "necessary"}:
            return "MEDIUM-consistent", "medium_minimal_scope_consistent"
        return "MEDIUM-consistent", "medium_minimal_scope_residual"
    return "MEDIUM-consistent", "medium_fallback"


def collect_dataset(processed_root: Path) -> Dict[str, Any]:
    app_dirs = list(_iter_app_dirs(processed_root))

    app_stage_counts = Counter()
    decision_counts = Counter()
    risk_counts = Counter()
    derived_risk_counts = Counter()
    ui_scene_counts = Counter()
    permission_counts = Counter()
    necessity_counts = Counter()
    consistency_counts = Counter()
    overscope_counts = Counter()
    scene_risk_matrix: Dict[str, Counter] = defaultdict(Counter)
    risk_reason_matrix: Dict[str, Counter] = defaultdict(Counter)
    scene_reason_matrix: Dict[str, Counter] = defaultdict(Counter)
    medium_triple_counts = Counter()
    derived_risk_reasons = Counter()
    reason_counts = Counter()
    chains_per_app: List[Dict[str, Any]] = []

    total_chain_png_files = 0
    total_result_chains = 0
    total_final_chains = 0

    for app_dir in app_dirs:
        result_path = app_dir / "result.json"
        permission_path = app_dir / "result_permission.json"
        semantic_path = app_dir / "result_semantic_v2.json"
        llm_path = app_dir / "result_llm_review.json"
        final_path = app_dir / "result_final_decision.json"

        if result_path.exists():
            app_stage_counts["result_json"] += 1
        if permission_path.exists():
            app_stage_counts["permission"] += 1
        if semantic_path.exists():
            app_stage_counts["semantic"] += 1
        if llm_path.exists():
            app_stage_counts["llm"] += 1
        if final_path.exists():
            app_stage_counts["final"] += 1

        chain_png_count = len(list(app_dir.glob("chain_*.png")))
        total_chain_png_files += chain_png_count

        result_chain_count = 0
        if result_path.exists():
            try:
                result_rows = _load_json(result_path)
                if isinstance(result_rows, list):
                    result_chain_count = len(result_rows)
            except Exception:
                result_chain_count = 0
        total_result_chains += result_chain_count

        final_chain_count = 0
        if final_path.exists():
            try:
                final_rows = _load_json(final_path)
            except Exception:
                final_rows = []
            if isinstance(final_rows, list):
                final_chain_count = len(final_rows)
                total_final_chains += final_chain_count
                for row in final_rows:
                    if not isinstance(row, dict):
                        continue
                    decision = str(row.get("final_decision", "") or "").strip() or "UNKNOWN"
                    risk = str(row.get("final_risk", "") or "").strip() or "UNKNOWN"
                    ui_scene = str(row.get("ui_task_scene", "") or "").strip() or "未知场景"
                    permissions = row.get("permissions") if isinstance(row.get("permissions"), list) else []

                    decision_counts[decision] += 1
                    risk_counts[risk] += 1
                    ui_scene_counts[ui_scene] += 1
                    scene_risk_matrix[ui_scene][risk] += 1
                    derived_bucket, derived_reason = _derive_medium_bucket(row)
                    derived_risk_counts[derived_bucket] += 1
                    derived_risk_reasons[derived_reason] += 1

                    for permission in permissions:
                        permission_text = str(permission or "").strip()
                        if permission_text:
                            permission_counts[permission_text] += 1

                    necessity = row.get("necessity") if isinstance(row.get("necessity"), dict) else {}
                    consistency = row.get("consistency") if isinstance(row.get("consistency"), dict) else {}
                    overscope = row.get("over_scope") if isinstance(row.get("over_scope"), dict) else {}
                    necessity_label = str(necessity.get("label", "") or "unknown")
                    consistency_label = str(consistency.get("label", "") or "unknown")
                    overscope_label = str(overscope.get("label", "") or "unknown")
                    necessity_counts[necessity_label] += 1
                    consistency_counts[consistency_label] += 1
                    overscope_counts[overscope_label] += 1
                    reason_flags: List[str] = []
                    if overscope_label in {"potentially_over_scoped", "over_scoped"}:
                        reason_flags.append("overreach")
                    if necessity_label in {"helpful", "unnecessary"}:
                        reason_flags.append("weak_necessity")
                    if consistency_label in {"weakly_consistent", "inconsistent"}:
                        reason_flags.append("inconsistency")
                    for reason in reason_flags:
                        reason_counts[reason] += 1
                        risk_reason_matrix[risk][reason] += 1
                        scene_reason_matrix[ui_scene][reason] += 1
                    if risk == "MEDIUM":
                        medium_triple_counts[(necessity_label, consistency_label, overscope_label)] += 1

        chains_per_app.append(
            {
                "app_dir_name": app_dir.name,
                "chain_png_count": chain_png_count,
                "result_chain_count": result_chain_count,
                "final_chain_count": final_chain_count,
            }
        )

    final_chain_values = [item["final_chain_count"] for item in chains_per_app if item["final_chain_count"] > 0]
    top_apps = sorted(chains_per_app, key=lambda x: x["final_chain_count"], reverse=True)[:TOP_N_APPS]
    top_ui_scenes = ui_scene_counts.most_common(TOP_N_SCENES)
    top_permissions = permission_counts.most_common(TOP_N_PERMISSIONS)
    total_permission_mentions = sum(permission_counts.values())

    top_scene_names = [name for name, _ in top_ui_scenes]
    scene_heatmap_rows: List[List[int]] = []
    for scene_name in top_scene_names:
        row = [scene_risk_matrix[scene_name].get(risk, 0) for risk in FINAL_RISK_ORDER]
        scene_heatmap_rows.append(row)
    scene_reason_rows: List[List[int]] = []
    for scene_name in top_scene_names:
        row = [scene_reason_matrix[scene_name].get(reason, 0) for reason in REASON_ORDER]
        scene_reason_rows.append(row)
    total_reason_mentions = sum(reason_counts.values())

    summary = {
        "processed_root": str(processed_root.resolve()),
        "apps": {
            "total_dirs": len(app_dirs),
            "with_result_json": app_stage_counts["result_json"],
            "with_result_permission": app_stage_counts["permission"],
            "with_result_semantic_v2": app_stage_counts["semantic"],
            "with_result_llm_review": app_stage_counts["llm"],
            "with_result_final_decision": app_stage_counts["final"],
        },
        "chains": {
            "total_chain_png_files": total_chain_png_files,
            "total_chains_from_result_json": total_result_chains,
            "total_chains_with_final_decision": total_final_chains,
            "total_permission_mentions": total_permission_mentions,
            "total_reason_mentions": total_reason_mentions,
        },
        "final_chain_distribution": {
            "min": min(final_chain_values) if final_chain_values else 0,
            "median": median(final_chain_values) if final_chain_values else 0,
            "avg": round(sum(final_chain_values) / len(final_chain_values), 2) if final_chain_values else 0.0,
            "max": max(final_chain_values) if final_chain_values else 0,
        },
        "final_decision_distribution": [
            {"label": label, "count": decision_counts.get(label, 0), "ratio": _safe_ratio(decision_counts.get(label, 0), total_final_chains)}
            for label in FINAL_DECISION_ORDER
        ],
        "final_risk_distribution": [
            {"label": label, "count": risk_counts.get(label, 0), "ratio": _safe_ratio(risk_counts.get(label, 0), total_final_chains)}
            for label in FINAL_RISK_ORDER
        ],
        "derived_risk_distribution": [
            {"label": label, "count": derived_risk_counts.get(label, 0), "ratio": _safe_ratio(derived_risk_counts.get(label, 0), total_final_chains)}
            for label in DERIVED_RISK_ORDER
        ],
        "top_ui_task_scenes": [
            {
                "ui_task_scene": name,
                "ui_task_scene_en": _scene_label_en(name),
                "count": count,
                "ratio": _safe_ratio(count, total_final_chains),
            }
            for name, count in top_ui_scenes
        ],
        "top_permissions": [
            {
                "permission": name,
                "count": count,
                "ratio_over_permission_mentions": _safe_ratio(count, total_permission_mentions),
                "ratio_over_chains": _safe_ratio(count, total_final_chains),
            }
            for name, count in top_permissions
        ],
        "judge_breakdown": {
            "necessity": dict(necessity_counts),
            "consistency": dict(consistency_counts),
            "over_scope": dict(overscope_counts),
        },
        "reason_distribution": [
            {"label": reason, "label_en": REASON_LABELS[reason], "count": reason_counts.get(reason, 0), "ratio": _safe_ratio(reason_counts.get(reason, 0), total_reason_mentions)}
            for reason in REASON_ORDER
        ],
        "reason_by_risk": {
            "risks": FINAL_RISK_ORDER,
            "reasons": REASON_ORDER,
            "reason_labels_en": [REASON_LABELS[reason] for reason in REASON_ORDER],
            "matrix": [[risk_reason_matrix[risk].get(reason, 0) for reason in REASON_ORDER] for risk in FINAL_RISK_ORDER],
        },
        "medium_subtype_breakdown": {
            "mapping": {
                "weak_or_partial_necessity": "helpful",
                "consistent_true": ["consistent", "weakly_consistent"],
                "overreach_true": ["potentially_over_scoped", "over_scoped"],
                "overreach_false": "minimal",
            },
            "derived_reason_counts": dict(derived_risk_reasons),
            "medium_top_triples": [
                {
                    "necessity": key[0],
                    "consistency": key[1],
                    "over_scope": key[2],
                    "count": count,
                }
                for key, count in medium_triple_counts.most_common(10)
            ],
        },
        "top_apps_by_final_chain_count": top_apps,
        "scene_risk_heatmap": {
            "scenes": top_scene_names,
            "scenes_en": [_scene_label_en(name) for name in top_scene_names],
            "risks": FINAL_RISK_ORDER,
            "matrix": scene_heatmap_rows,
        },
        "scene_reason_heatmap": {
            "scenes": top_scene_names,
            "scenes_en": [_scene_label_en(name) for name in top_scene_names],
            "reasons": REASON_ORDER,
            "reason_labels_en": [REASON_LABELS[reason] for reason in REASON_ORDER],
            "matrix": scene_reason_rows,
        },
        "all_apps": chains_per_app,
    }
    return summary


def _annotate_vertical_bars(ax: plt.Axes, values: List[int], texts: List[str]) -> None:
    y_max = max(values) if values else 0
    for index, (value, text) in enumerate(zip(values, texts)):
        ax.text(
            index,
            value + max(1.0, y_max * 0.02),
            text,
            ha="center",
            va="bottom",
            fontsize=9,
        )


def _pie_autopct(values: List[int]) -> Callable[[float], str]:
    total = sum(values)

    def _formatter(pct: float) -> str:
        count = int(round(pct * total / 100.0))
        if count <= 0:
            return ""
        return f"{pct:.1f}%\n(n={count})"

    return _formatter


def plot_reason_distribution(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["reason_distribution"]
    labels = [row["label_en"] for row in rows]
    values = [row["count"] for row in rows]
    colors = [REASON_COLORS.get(row["label"], "#777777") for row in rows]

    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    wedges, _, _ = ax.pie(
        values,
        colors=colors,
        startangle=90,
        autopct=_pie_autopct(values),
        textprops={"fontsize": 10},
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )
    ax.set_title("Risk Reason Distribution")
    ax.legend(wedges, labels, title="Reason", loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_decision_distribution(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["final_decision_distribution"]
    labels = [row["label"] for row in rows]
    values = [row["count"] for row in rows]
    colors = [DECISION_COLORS.get(label, "#777777") for label in labels]

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    wedges, _, _ = ax.pie(
        values,
        colors=colors,
        startangle=90,
        autopct=_pie_autopct(values),
        textprops={"fontsize": 10},
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )
    ax.set_title("RQ3 Final Decision Distribution")
    ax.legend(wedges, labels, title="Decision", loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_risk_distribution(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["derived_risk_distribution"]
    labels = [row["label"] for row in rows]
    values = [row["count"] for row in rows]
    colors = [DERIVED_RISK_COLORS.get(label, "#777777") for label in labels]

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    wedges, _, _ = ax.pie(
        values,
        colors=colors,
        startangle=90,
        autopct=_pie_autopct(values),
        textprops={"fontsize": 10},
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )
    ax.set_title("RQ3 Paper Risk Breakdown")
    ax.legend(wedges, labels, title="Risk Bucket", loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_top_ui_scenes(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["top_ui_task_scenes"]
    labels = [row["ui_task_scene_en"] for row in rows]
    values = [row["count"] for row in rows]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(11.0, 6.2))
    ax.bar(x, values, color=SCENE_COLOR, width=0.68)
    ax.set_xticks(x, labels, rotation=28, ha="right")
    ax.set_ylabel("Chains")
    ax.set_title(f"Top {len(rows)} Coarse UI Task Scenes")
    ax.grid(axis="y", alpha=0.2)

    texts = [f"{value}\n({row['ratio'] * 100:.1f}%)" for value, row in zip(values, rows)]
    _annotate_vertical_bars(ax, values, texts)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_top_permissions(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["top_permissions"]
    labels = [row["permission"] for row in rows]
    values = [row["count"] for row in rows]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(11.8, 6.4))
    ax.bar(x, values, color=PERMISSION_COLOR, width=0.68)
    ax.set_xticks(x, labels, rotation=38, ha="right")
    ax.set_ylabel("Permission mentions")
    ax.set_title(f"Top {len(rows)} Requested Permissions")
    ax.grid(axis="y", alpha=0.2)

    texts = [f"{value}\n({row['ratio_over_permission_mentions'] * 100:.1f}%)" for value, row in zip(values, rows)]
    _annotate_vertical_bars(ax, values, texts)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_scene_risk_heatmap(summary: Dict[str, Any], out_path: Path) -> None:
    heatmap = summary["scene_risk_heatmap"]
    scenes = heatmap["scenes_en"]
    risks = heatmap["risks"]
    matrix = np.array(heatmap["matrix"], dtype=float)

    fig_h = max(5.2, 0.45 * len(scenes) + 1.8)
    fig, ax = plt.subplots(figsize=(8.8, fig_h))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(np.arange(len(risks)), risks)
    ax.set_yticks(np.arange(len(scenes)), scenes)
    ax.set_title("Final Risk by Coarse UI Task Scene")

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = int(matrix[i, j])
            ax.text(j, i, str(value), ha="center", va="center", fontsize=9, color="#1F1F1F")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Chains")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_reason_by_risk(summary: Dict[str, Any], out_path: Path) -> None:
    payload = summary["reason_by_risk"]
    risks = payload["risks"]
    reasons = payload["reasons"]
    matrix = np.array(payload["matrix"], dtype=float)

    x = np.arange(len(risks))
    width = 0.22

    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    for idx, reason in enumerate(reasons):
        offset = (idx - 1) * width
        values = matrix[:, idx]
        ax.bar(x + offset, values, width=width, color=REASON_COLORS[reason], label=REASON_LABELS[reason])
        y_max = matrix.max() if matrix.size else 0
        for x_i, value in zip(x + offset, values):
            ax.text(x_i, value + max(1.0, y_max * 0.015), str(int(value)), ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x, risks)
    ax.set_ylabel("Reason mentions")
    ax.set_title("Reason × Risk Level")
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_scene_reason_heatmap(summary: Dict[str, Any], out_path: Path) -> None:
    heatmap = summary["scene_reason_heatmap"]
    scenes = heatmap["scenes_en"]
    reasons = heatmap["reason_labels_en"]
    matrix = np.array(heatmap["matrix"], dtype=float)

    fig_h = max(5.2, 0.45 * len(scenes) + 1.8)
    fig, ax = plt.subplots(figsize=(8.8, fig_h))
    im = ax.imshow(matrix, cmap="Blues", aspect="auto")
    ax.set_xticks(np.arange(len(reasons)), reasons)
    ax.set_yticks(np.arange(len(scenes)), scenes)
    ax.set_title("Scene × Reason")

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = int(matrix[i, j])
            ax.text(j, i, str(value), ha="center", va="center", fontsize=9, color="#1F1F1F")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Reason mentions")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_chain_histogram(summary: Dict[str, Any], out_path: Path) -> None:
    values = [item["final_chain_count"] for item in summary["all_apps"] if item["final_chain_count"] > 0]
    if not values:
        return

    max_value = max(values)
    bins = min(15, max(6, int(math.sqrt(len(values))) + 2))

    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    ax.hist(values, bins=bins, color=HIST_COLOR, edgecolor="white")
    ax.set_xlabel("Final chains per app")
    ax.set_ylabel("Apps")
    ax.set_title("Distribution of Chains per App")
    ax.grid(axis="y", alpha=0.2)
    ax.set_xlim(left=0, right=max_value + 1)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_top_apps(summary: Dict[str, Any], out_path: Path) -> None:
    rows = summary["top_apps_by_final_chain_count"]
    labels = [row["app_dir_name"] for row in rows]
    values = [row["final_chain_count"] for row in rows]
    y_pos = np.arange(len(labels))

    fig_h = max(6.0, 0.42 * len(labels) + 2.0)
    fig, ax = plt.subplots(figsize=(12.5, fig_h))
    ax.barh(y_pos, values, color=APP_COLOR)
    ax.set_yticks(y_pos, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Final chains")
    ax.set_title(f"Top {len(rows)} Apps by Chain Count")
    ax.grid(axis="x", alpha=0.2)

    x_max = max(values) if values else 0
    for idx, value in enumerate(values):
        ax.text(value + max(0.2, x_max * 0.01), idx, str(value), va="center", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def write_markdown_summary(summary: Dict[str, Any], out_path: Path) -> None:
    lines = [
        "# RQ3 Processed Visualization Summary",
        "",
        f"- processed_root: `{summary['processed_root']}`",
        f"- app_dirs: {summary['apps']['total_dirs']}",
        f"- apps_with_final_decision: {summary['apps']['with_result_final_decision']}",
        f"- total_chains_from_result_json: {summary['chains']['total_chains_from_result_json']}",
        f"- total_chains_with_final_decision: {summary['chains']['total_chains_with_final_decision']}",
        "",
        "## Final Decision Distribution",
    ]

    for row in summary["final_decision_distribution"]:
        lines.append(f"- {row['label']}: {row['count']} ({row['ratio'] * 100:.1f}%)")

    lines.extend(["", "## Paper Risk Breakdown"])
    for row in summary["derived_risk_distribution"]:
        lines.append(f"- {row['label']}: {row['count']} ({row['ratio'] * 100:.1f}%)")

    lines.extend(["", "## Risk Reason Distribution"])
    lines.append(f"- Denominator for percentages here is total reason mentions: {summary['chains']['total_reason_mentions']}")
    for row in summary["reason_distribution"]:
        lines.append(f"- {row['label_en']}: {row['count']} ({row['ratio'] * 100:.1f}% of mentions)")

    lines.extend(["", "## Medium Split Mapping"])
    lines.append("- weak_or_partial_necessity -> `helpful`")
    lines.append("- consistent_true -> `consistent` or `weakly_consistent`")
    lines.append("- overreach_true -> `potentially_over_scoped` or `over_scoped`")
    lines.append("- overreach_false -> `minimal`")

    lines.extend(["", "## Top Coarse UI Task Scenes"])
    for row in summary["top_ui_task_scenes"]:
        lines.append(f"- {row['ui_task_scene_en']}: {row['count']} ({row['ratio'] * 100:.1f}%)")

    lines.extend(["", "## Top Permissions"])
    lines.append(f"- Denominator for percentages here is total permission mentions: {summary['chains']['total_permission_mentions']}")
    for row in summary["top_permissions"]:
        lines.append(f"- {row['permission']}: {row['count']} ({row['ratio_over_permission_mentions'] * 100:.1f}% of mentions)")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reusable RQ3 visualizations from processed phase3 outputs.")
    parser.add_argument("processed_root", help="processed root containing per-app result files")
    parser.add_argument("--output-dir", default="", help="output directory; default is <processed_root>/rq3_visualizations")
    args = parser.parse_args()

    processed_root = Path(args.processed_root).resolve()
    if not processed_root.is_dir():
        raise SystemExit(f"processed_root not found: {processed_root}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else processed_root / "rq3_visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = collect_dataset(processed_root)

    (output_dir / "rq3_visualization_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_summary(summary, output_dir / "rq3_visualization_summary.md")

    plot_decision_distribution(summary, output_dir / "rq3_final_decision_distribution.png")
    plot_risk_distribution(summary, output_dir / "rq3_final_risk_distribution.png")
    plot_reason_distribution(summary, output_dir / "rq3_risk_reason_distribution.png")
    plot_reason_by_risk(summary, output_dir / "rq3_reason_by_risk_level.png")
    plot_scene_reason_heatmap(summary, output_dir / "rq3_scene_reason_heatmap.png")
    plot_top_ui_scenes(summary, output_dir / "rq3_top_refined_scenes.png")
    plot_top_permissions(summary, output_dir / "rq3_top_permissions.png")
    plot_scene_risk_heatmap(summary, output_dir / "rq3_scene_decision_heatmap.png")
    plot_chain_histogram(summary, output_dir / "rq3_chain_count_histogram.png")
    plot_top_apps(summary, output_dir / "rq3_top_apps_by_chain_count.png")

    print(f"[DONE] output_dir={output_dir}")
    print(f"[DONE] apps={summary['apps']['with_result_final_decision']} total_chains={summary['chains']['total_chains_with_final_decision']}")


if __name__ == "__main__":
    main()
