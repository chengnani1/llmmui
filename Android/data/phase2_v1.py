import os
import re
import json
import hashlib
from collections import defaultdict
from typing import List, Optional
from PIL import Image
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pytesseract
import unicodedata
from tqdm import tqdm

# =========================================================
# PATH CONFIG
# =========================================================

RAW_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11/raw_full"
DST_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed"

STEP_RE = re.compile(r"step-(\d+)-.*\.png$")
FIXED_HEIGHT = 1600

# =========================================================
# IO
# =========================================================

def safe_mkdir(p: str):
    os.makedirs(p, exist_ok=True)

def read_json(p: str):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(o, p: str):
    safe_mkdir(os.path.dirname(p))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=2)

# =========================================================
# OCR
# =========================================================

def ocr_preprocess(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY, 31, 5
    )

def clean_ocr_text(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def ocr_image(image_path):
    bin_img = ocr_preprocess(image_path)
    if bin_img is None:
        return ""
    txt = pytesseract.image_to_string(
        Image.fromarray(bin_img),
        lang="chi_sim"
    )
    return clean_ocr_text(txt)

# =========================================================
# XML / widgets
# =========================================================

def parse_widgets(xml_path: str):
    if not os.path.exists(xml_path):
        return []
    try:
        root = ET.fromstring(open(xml_path, encoding="utf-8").read())
    except Exception:
        return []

    widgets = []

    def dfs(n, depth=0):
        widgets.append({
            "text": n.attrib.get("text", "") or "",
            "class": n.attrib.get("class", "") or "",
            "resource-id": n.attrib.get("resource-id", "") or "",
            "depth": depth,
        })
        for c in n:
            dfs(c, depth + 1)

    dfs(root)
    return widgets

def widget_score(w):
    score = 0
    if w["text"]:
        score += 2
        if any(k in w["text"] for k in ["允许", "拒绝", "权限"]):
            score += 5
    if "permission" in w["resource-id"].lower():
        score += 8
    score += max(0, 5 - w["depth"]) * 0.5
    return score

def enrich_widgets(xml_path):
    ws = parse_widgets(xml_path)
    for w in ws:
        w["score"] = widget_score(w)
    ws.sort(key=lambda x: x["score"], reverse=True)
    return ws

# =========================================================
# Permission detection（兼容 rid / resource-id）
# =========================================================

def contains_permission_word(ws):
    texts = [w.get("text", "") for w in ws]
    rids = " ".join(
        (w.get("rid") or w.get("resource-id") or "").lower()
        for w in ws
    )
    if "permission" in rids:
        return True
    if any("允许" in t or "拒绝" in t for t in texts):
        return True
    return False

def is_system_permission(ws) -> bool:
    texts = [w.get("text", "") for w in ws]
    if not (any("允许" in t for t in texts) and any("拒绝" in t for t in texts)):
        return False

    rids = " ".join(
        (w.get("rid") or w.get("resource-id") or "").lower()
        for w in ws
    )
    return any(k in rids for k in [
        "permission_group_title",
        "permission_allow",
        "permission_deny",
        "permissioncontroller",
        "miui"
    ])

def permission_signature(ws) -> str:
    parts = []
    for w in ws:
        rid = (w.get("rid") or w.get("resource-id") or "").lower()
        txt = w.get("text", "")
        if "permission" in rid or "miui" in rid:
            parts.append(rid + ":" + txt)
    return "|".join(parts)

# =========================================================
# step index
# =========================================================

def build_step_index(app_dir: str):
    idx2png = {}
    for f in os.listdir(app_dir):
        m = STEP_RE.match(f)
        if m:
            idx2png[int(m.group(1))] = f
    return sorted(idx2png), idx2png

# =========================================================
# Image merge
# =========================================================

def normalize_to_portrait(im: Image.Image) -> Image.Image:
    if im.width > im.height:
        im = im.rotate(90, expand=True)
    return im

def merge_images(imgs: List[str], out: str):
    ims = []
    for p in imgs:
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            ims.append(normalize_to_portrait(im))

    if not ims:
        return

    resized = []
    for im in ims:
        w, h = im.size
        new_w = int(w * FIXED_HEIGHT / h)
        resized.append(im.resize((new_w, FIXED_HEIGHT)))

    canvas = Image.new(
        "RGB",
        (sum(im.width for im in resized), FIXED_HEIGHT),
        (255, 255, 255)
    )

    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width

    safe_mkdir(os.path.dirname(out))
    canvas.save(out)

# =========================================================
# repair_chain（保持你验证过的版本）
# =========================================================

def repair_chain(app_dir, steps, idx2png, seq) -> Optional[List[str]]:
    b_idx = int(STEP_RE.match(seq[0]).group(1))
    ws = parse_widgets(os.path.join(app_dir, seq[0].replace(".png", ".xml")))
    start = b_idx

    if contains_permission_word(ws):
        found = False
        for d in range(1, 4):
            if b_idx - d not in idx2png:
                break
            p = idx2png[b_idx - d]
            ws2 = parse_widgets(os.path.join(app_dir, p.replace(".png", ".xml")))
            if not contains_permission_word(ws2):
                start = b_idx - d
                found = True
                break
        if not found:
            return None

    a_idx = int(STEP_RE.match(seq[-1]).group(1))
    ws = parse_widgets(os.path.join(app_dir, seq[-1].replace(".png", ".xml")))
    end = a_idx

    if is_system_permission(ws):
        found = False
        for d in range(1, 4):
            if a_idx + d not in idx2png:
                break
            p = idx2png[a_idx + d]
            ws2 = parse_widgets(os.path.join(app_dir, p.replace(".png", ".xml")))
            if not is_system_permission(ws2):
                end = a_idx + d
                found = True
                break
        if not found:
            return None

    full = [idx2png[i] for i in range(start, end + 1) if i in idx2png]
    if len(full) < 3:
        return None

    sys = []
    for p in full[1:-1]:
        ws = parse_widgets(os.path.join(app_dir, p.replace(".png", ".xml")))
        if is_system_permission(ws):
            sig = permission_signature(ws)
            sys.append((p, sig))

    if not sys:
        return None

    best = {}
    for p, sig in sys:
        best[sig] = p   # 保留靠后的

    grant = sorted(best.values(), key=lambda x: int(STEP_RE.match(x).group(1)))
    return [full[0]] + grant + [full[-1]]

# =========================================================
# Main
# =========================================================

def main():
    safe_mkdir(DST_ROOT)
    stat = defaultdict(int)

    for app in tqdm(sorted(os.listdir(RAW_ROOT)), desc="APKs"):
        app_dir = os.path.join(RAW_ROOT, app)
        if not os.path.isdir(app_dir):
            continue

        tp = os.path.join(app_dir, "tupleOfPermissions.json")
        if not os.path.exists(tp):
            continue

        raw = read_json(tp)
        if not raw:
            continue

        steps, idx2png = build_step_index(app_dir)

        result = []
        new_tp = []
        cid = 0

        for seq in raw:
            stat["total"] += 1
            repaired = repair_chain(app_dir, steps, idx2png, seq)
            if repaired is None:
                stat["removed"] += 1
                continue

            stat["kept"] += 1

            def build_entry(p):
                img = os.path.join(app_dir, p)
                xml = img.replace(".png", ".xml")
                return {
                    "file": p,
                    "feature": {
                        "text": ocr_image(img),
                        "widgets": enrich_widgets(xml),
                    }
                }

            item = {
                "chain_id": cid,
                "ui_before_grant": build_entry(repaired[0]),
                "ui_granting": [build_entry(p) for p in repaired[1:-1]],
                "ui_after_grant": build_entry(repaired[-1]),
            }

            result.append(item)
            new_tp.append(repaired)
            cid += 1

        if not result:
            continue  # ★ 不创建空文件夹

        out_app = os.path.join(DST_ROOT, app)
        safe_mkdir(out_app)

        for i, chain in enumerate(new_tp):
            imgs = [os.path.join(app_dir, p) for p in chain]
            merge_images(imgs, os.path.join(out_app, f"chain_{i}.png"))

        write_json(result, os.path.join(out_app, "result.json"))
        write_json(new_tp, os.path.join(out_app, "tupleOfPermissions.json"))

    write_json(dict(stat), os.path.join(DST_ROOT, "summary.json"))
    print("DONE:", dict(stat))

if __name__ == "__main__":
    main()