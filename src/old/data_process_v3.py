import os
import re
import json
import hashlib
import shutil
from typing import List, Dict, Optional
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image
import pytesseract
import unicodedata
from xml.etree import ElementTree as ET

from tqdm import tqdm   # ⭐ 进度条

# =========================================================
# PATH CONFIG
# =========================================================

RAW_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11/raw"
PROCESSED_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed"

STEP_RE = re.compile(r"step-(\d+)-.*\.png$")
FIXED_HEIGHT = 1600   # ★ 强制所有截图“竖图化”

# =========================================================
# Permission / Widget Config
# =========================================================

IMPORTANT_CLASSES = {
    "android.widget.TextView",
    "android.widget.Button",
    "android.widget.ImageButton",
    "android.widget.CheckedTextView",
    "android.widget.EditText",
}

KEYWORDS = [
    "允许", "拒绝", "权限", "授权", "访问", "使用",
    "仅在使用中", "本次运行", "始终允许",
    "位置", "相机", "麦克风", "录音", "联系人", "存储"
]

# =========================================================
# Basic IO
# =========================================================

def safe_mkdir(p):
    os.makedirs(p, exist_ok=True)

def read_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(o, p):
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
    gamma = 1.5
    table = ((np.arange(256) / 255.0) ** (1 / gamma) * 255).astype("uint8")
    gray = cv2.LUT(gray, table)
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
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9，。？！：:+-]", "", text)
    return text.replace(" ", "").strip()

def ocr_image(image_path):
    bin_img = ocr_preprocess(image_path)
    if bin_img is None:
        return ""
    results = []
    for scale in [1.0, 1.5, 2.0]:
        resized = cv2.resize(bin_img, None, fx=scale, fy=scale)
        txt = pytesseract.image_to_string(Image.fromarray(resized), "chi_sim")
        results.append(txt)
    return clean_ocr_text("\n".join(results))

# =========================================================
# XML / Widget Parsing + Scoring
# =========================================================

def parse_widgets(xml_path):
    if not os.path.exists(xml_path):
        return []
    try:
        root = ET.fromstring(open(xml_path, encoding="utf-8").read())
    except:
        return []

    widgets = []

    def dfs(node, depth=0):
        widgets.append({
            "text": node.attrib.get("text", "") or "",
            "class": node.attrib.get("class", "") or "",
            "resource-id": node.attrib.get("resource-id", "") or "",
            "depth": depth,
        })
        for c in node:
            dfs(c, depth + 1)

    dfs(root)
    return widgets

def score_widget(w):
    score = 0
    if w["text"]:
        score += 2
        if any(k in w["text"] for k in KEYWORDS):
            score += 6
    if "permission" in w["resource-id"].lower():
        score += 8
    if w["class"] in IMPORTANT_CLASSES:
        score += 2
    score += max(0, 5 - w["depth"]) * 0.5
    return score

def select_top_widgets(xml_path, topk=20):
    ws = parse_widgets(xml_path)
    ws.sort(key=score_widget, reverse=True)
    return ws[:topk]

# =========================================================
# Permission UI Detection (NO OCR)
# =========================================================

def is_system_permission(widgets):
    texts = [w["text"] for w in widgets]
    if not (any("允许" in t for t in texts) and any("拒绝" in t for t in texts)):
        return False

    rid_blob = " ".join(w["resource-id"].lower() for w in widgets)
    if any(k in rid_blob for k in [
        "permission_group_title",
        "permission_allow",
        "permission_deny",
        "permissioncontroller",
        "miui"
    ]):
        return True

    return True

def permission_signature(widgets):
    sig = []
    for w in widgets:
        rid = w["resource-id"].lower()
        if "permission" in rid or "miui" in rid:
            sig.append(rid + ":" + w["text"])
    return "|".join(sig)

# =========================================================
# Step index helpers
# =========================================================

def build_step_index(app_dir):
    idx2png = {}
    for f in os.listdir(app_dir):
        m = STEP_RE.match(f)
        if m:
            idx2png[int(m.group(1))] = f
    return sorted(idx2png), idx2png

# =========================================================
# Image merge (ALL → vertical resized → horizontal merge)
# =========================================================

def merge_images(img_paths, out_path):
    ims = []
    for p in img_paths:
        if os.path.exists(p):
            ims.append(Image.open(p).convert("RGB"))
    if not ims:
        return

    resized = []
    for im in ims:
        w, h = im.size
        new_w = int(w * FIXED_HEIGHT / h)
        resized.append(im.resize((new_w, FIXED_HEIGHT)))

    total_w = sum(im.width for im in resized)
    canvas = Image.new("RGB", (total_w, FIXED_HEIGHT), (255, 255, 255))

    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width

    canvas.save(out_path)

# =========================================================
# Chain Repair Logic
# =========================================================

def repair_chain(app_dir, steps, idx2png, seq) -> Optional[List[str]]:
    if len(seq) < 3:
        return None

    def contains_permission_word(xml):
        ws = parse_widgets(xml)
        return any("权限" in w["text"] for w in ws)

    b_idx = int(STEP_RE.match(seq[0]).group(1))
    start = b_idx
    if contains_permission_word(os.path.join(app_dir, seq[0].replace(".png", ".xml"))):
        ok = False
        for d in range(1, 4):
            if b_idx - d not in idx2png:
                break
            cand = idx2png[b_idx - d]
            if not contains_permission_word(os.path.join(app_dir, cand.replace(".png", ".xml"))):
                start = b_idx - d
                ok = True
                break
        if not ok:
            return None

    a_idx = int(STEP_RE.match(seq[-1]).group(1))
    end = a_idx
    ws_after = parse_widgets(os.path.join(app_dir, seq[-1].replace(".png", ".xml")))
    if is_system_permission(ws_after):
        ok = False
        for d in range(1, 4):
            if a_idx + d not in idx2png:
                break
            cand = idx2png[a_idx + d]
            ws2 = parse_widgets(os.path.join(app_dir, cand.replace(".png", ".xml")))
            if not is_system_permission(ws2):
                end = a_idx + d
                ok = True
                break
        if not ok:
            return None

    full = [idx2png[i] for i in range(start, end + 1) if i in idx2png]
    if len(full) < 3:
        return None

    perms = []
    for p in full[1:-1]:
        ws = parse_widgets(os.path.join(app_dir, p.replace(".png", ".xml")))
        if is_system_permission(ws):
            perms.append((p, permission_signature(ws)))

    if not perms:
        return None

    uniq = {}
    for p, sig in perms:
        if sig not in uniq:
            uniq[sig] = p

    final = [full[0]] + list(uniq.values()) + [full[-1]]
    return final if len(final) >= 3 else None

# =========================================================
# Fingerprint
# =========================================================

def compute_chain_fingerprint(item):
    def norm(t):
        return re.sub(r"\s+", "", t or "").lower()
    before = norm(item["ui_before_grant"]["feature"]["text"])
    grant = norm(item["ui_granting"][0]["feature"]["text"]) if item["ui_granting"] else ""
    after = norm(item["ui_after_grant"]["feature"]["text"])
    return hashlib.md5(f"{before}|{grant}|{after}".encode()).hexdigest()

# =========================================================
# Main
# =========================================================

def main():
    safe_mkdir(PROCESSED_ROOT)

    apps = sorted([d for d in os.listdir(RAW_ROOT) if os.path.isdir(os.path.join(RAW_ROOT, d))])

    for app in tqdm(apps, desc="Processing apps"):
        app_dir = os.path.join(RAW_ROOT, app)

        tp = os.path.join(app_dir, "tupleOfPermissions.json")
        if not os.path.exists(tp):
            continue

        raw = read_json(tp)
        if not raw:
            continue

        steps, idx2png = build_step_index(app_dir)
        if not steps:
            continue

        out_app = os.path.join(PROCESSED_ROOT, app)
        safe_mkdir(out_app)

        new_result = []
        new_tp = []
        cid = 0

        for seq in tqdm(raw, desc=f"{app} chains", leave=False):
            repaired = repair_chain(app_dir, steps, idx2png, seq)
            if repaired is None:
                continue

            item = {
                "chain_id": cid,
                "ui_before_grant": None,
                "ui_granting": [],
                "ui_after_grant": None,
            }

            for i, p in enumerate(repaired):
                img_path = os.path.join(app_dir, p)
                xml_path = img_path.replace(".png", ".xml")

                entry = {
                    "file": p,
                    "feature": {
                        "text": ocr_image(img_path),
                        "widgets": select_top_widgets(xml_path),
                    }
                }

                if i == 0:
                    item["ui_before_grant"] = entry
                elif i == len(repaired) - 1:
                    item["ui_after_grant"] = entry
                else:
                    item["ui_granting"].append(entry)

                shutil.copy2(img_path, os.path.join(out_app, p))
                shutil.copy2(xml_path, os.path.join(out_app, p.replace(".png", ".xml")))

            item["chain_fingerprint"] = compute_chain_fingerprint(item)
            new_result.append(item)
            new_tp.append(repaired)

            imgs = [os.path.join(out_app, p) for p in repaired]
            merge_images(imgs, os.path.join(out_app, f"chain_{cid}.png"))

            cid += 1

        if new_result:
            write_json(new_result, os.path.join(out_app, "result.json"))
            write_json(new_tp, os.path.join(out_app, "tupleOfPermissions.json"))

    print("Phase-2 DONE")

if __name__ == "__main__":
    main()