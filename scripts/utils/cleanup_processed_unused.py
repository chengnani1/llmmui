#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List

ROOT_KEEP_FILES = {
    "phase3_v2_summary.json",
    "phase3_v2_compliance_summary.json",
    "phase3_v2_final_summary.json",
    "judge_binary_metrics_after.json",
}

APP_KEEP_EXACT = {
    "result.json",
    "result_permission.json",
    "result_semantic_v2.json",
    "result_retrieved_knowledge.json",
    "result_llm_review.json",
    "result_final_decision.json",
    "label_judge.json",
    "labels_permission.json",
}


@dataclass
class MoveRecord:
    src: str
    dst: str


def is_app_dir(p: Path) -> bool:
    return p.is_dir() and (p / "result.json").is_file()


def is_chain_png(name: str) -> bool:
    if not name.startswith("chain_") or not name.endswith(".png"):
        return False
    mid = name[len("chain_") : -len(".png")]
    return mid.isdigit()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def move_file(src: Path, dst: Path, dry_run: bool) -> None:
    ensure_parent(dst)
    if dry_run:
        return
    shutil.move(str(src), str(dst))


def cleanup(processed_root: Path, dry_run: bool = False) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = processed_root / f"_archive_cleanup_{ts}"

    moved_root: List[MoveRecord] = []
    moved_app: List[MoveRecord] = []
    moved_extra_dirs: List[MoveRecord] = []
    removed_ds_store: List[str] = []

    # Root-level cleanup (files only)
    for child in sorted(processed_root.iterdir()):
        if child.name.startswith("_archive_cleanup_"):
            continue
        if child.is_file():
            if child.name == ".DS_Store":
                if not dry_run:
                    child.unlink(missing_ok=True)
                removed_ds_store.append(str(child))
                continue
            if child.name not in ROOT_KEEP_FILES:
                dst = archive_dir / "root" / child.name
                move_file(child, dst, dry_run)
                moved_root.append(MoveRecord(str(child), str(dst)))

    # App-level cleanup
    for app_dir in sorted(processed_root.iterdir()):
        if app_dir.name.startswith("_archive_cleanup_"):
            continue
        if not is_app_dir(app_dir):
            continue

        for f in sorted(app_dir.iterdir()):
            if not f.is_file():
                continue
            if f.name == ".DS_Store":
                if not dry_run:
                    f.unlink(missing_ok=True)
                removed_ds_store.append(str(f))
                continue

            keep = f.name in APP_KEEP_EXACT or is_chain_png(f.name)
            if keep:
                continue

            dst = archive_dir / "apps" / app_dir.name / f.name
            move_file(f, dst, dry_run)
            moved_app.append(MoveRecord(str(f), str(dst)))

    # Extra root directories cleanup (non-app historical artifacts)
    for child in sorted(processed_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_archive_cleanup_"):
            continue
        if is_app_dir(child):
            continue
        dst = archive_dir / "extra_dirs" / child.name
        if not dry_run:
            ensure_parent(dst / ".keep")
            shutil.move(str(child), str(dst))
        moved_extra_dirs.append(MoveRecord(str(child), str(dst)))

    report = {
        "processed_root": str(processed_root),
        "archive_dir": str(archive_dir),
        "dry_run": dry_run,
        "moved_root_count": len(moved_root),
        "moved_app_count": len(moved_app),
        "removed_ds_store_count": len(removed_ds_store),
        "moved_extra_dirs_count": len(moved_extra_dirs),
        "moved_root": [asdict(x) for x in moved_root],
        "moved_app": [asdict(x) for x in moved_app],
        "moved_extra_dirs": [asdict(x) for x in moved_extra_dirs],
        "removed_ds_store": removed_ds_store,
    }

    if not dry_run:
        ensure_parent(archive_dir / "cleanup_report.json")
        with (archive_dir / "cleanup_report.json").open("w", encoding="utf-8") as wf:
            json.dump(report, wf, ensure_ascii=False, indent=2)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean unused files under data/processed by moving to archive")
    parser.add_argument("processed_root", nargs="?", default="data/processed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.processed_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"processed_root not found: {root}")

    report = cleanup(root, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
