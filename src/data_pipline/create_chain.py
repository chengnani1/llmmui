import os
import re
import json
from collections import defaultdict
from typing import List, Optional
from PIL import Image
from xml.etree import ElementTree as ET

from tqdm import tqdm

RAW_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11/raw_full"
DST_ROOT = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed_new"

STEP_RE = re.compile(r"step-(\d+)-.*\.png$")
FIXED_HEIGHT = 1600   # ★ 强制所有图“竖化”

# =========================================================
# 基础 IO
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
# XML / 权限识别（无 OCR）
# =========================================================

def parse_widgets(xml_path: str):
    if not os.path.exists(xml_path):
        return []
    try:
        root = ET.fromstring(open(xml_path, encoding="utf-8").read())
    except Exception:
        return []
    ws = []

    def dfs(n):
        ws.append({
            "text": n.attrib.get("text", "") or "",
            "rid": n.attrib.get("resource-id", "") or "",
        })
        for c in n:
            dfs(c)

    dfs(root)
    return ws

def contains_permission_word(ws):
    texts = [w["text"] for w in ws]
    rids = " ".join(w["rid"].lower() for w in ws)

    # 必须同时满足至少一个“系统特征”
    if any("permission" in rids for _ in [0]):
        return True

    # 或明确出现“允许 / 拒绝”
    if any("允许" in t for t in texts) or any("拒绝" in t for t in texts):
        return True

    return False
def is_system_permission(ws) -> bool:
    texts = [w["text"] for w in ws]
    has_allow = any("允许" in t for t in texts)
    has_deny = any("拒绝" in t for t in texts)
    if not (has_allow and has_deny):
        return False

    rids = " ".join(w["rid"].lower() for w in ws)
    if any(k in rids for k in [
        "permission_group_title",
        "permission_allow",
        "permission_deny",
        "permissioncontroller",
        "miui"
    ]):
        return True

    # fallback：只要“允许 + 拒绝”同时存在
    #return True

def permission_signature(ws) -> str:
    parts = []
    for w in ws:
        rid = w["rid"].lower()
        txt = w["text"]
        if "permission" in rid or "miui" in rid:
            parts.append(rid + ":" + txt)
    if parts:
        return "|".join(parts)
    return "|".join(w["text"] for w in ws if "权限" in w["text"])

def clarity_score(ws, img_path: str) -> float:
    score = 0.0
    score += len(ws)
    texts = [w["text"] for w in ws]
    if any("允许" in t for t in texts) and any("拒绝" in t for t in texts):
        score += 5.0
    try:
        im = Image.open(img_path)
        score += (im.width * im.height) / 1e6
    except Exception:
        pass
    return score

# =========================================================
# step 索引
# =========================================================

def build_step_index(app_dir: str):
    idx2png = {}
    for f in os.listdir(app_dir):
        m = STEP_RE.match(f)
        if m:
            idx2png[int(m.group(1))] = f
    return sorted(idx2png), idx2png

# =========================================================
# 拼图（严格竖图 → 横拼）【改点2：横屏先旋转成竖屏】
# =========================================================

def normalize_to_portrait(im: Image.Image) -> Image.Image:
    # 横屏（w>h）统一旋转成竖屏；expand=True 防止裁切
    w, h = im.size
    if w > h:
        im = im.rotate(90, expand=True)
    return im

def merge_images(imgs: List[str], out: str):
    ims = []
    for p in imgs:
        if os.path.exists(p):
            try:
                im = Image.open(p).convert("RGB")
                im = normalize_to_portrait(im)  # ★ 横屏 → 竖屏
                ims.append(im)
            except Exception:
                continue

    if not ims:
        return

    resized = []
    for im in ims:
        w, h = im.size
        if h <= 0:
            continue
        new_w = int(w * FIXED_HEIGHT / h)
        if new_w <= 0:
            continue
        resized.append(im.resize((new_w, FIXED_HEIGHT)))

    if not resized:
        return

    total_w = sum(im.width for im in resized)
    canvas = Image.new("RGB", (total_w, FIXED_HEIGHT), (255, 255, 255))

    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width

    safe_mkdir(os.path.dirname(out))
    canvas.save(out)

# =========================================================
# 核心 chain 修复（最终封闭版）
# =========================================================

def repair_chain(app_dir: str, steps, idx2png: dict, seq: List[str]) -> Optional[List[str]]:
    # ---------- before ----------
    b_idx = int(STEP_RE.match(seq[0]).group(1))
    ws = parse_widgets(os.path.join(app_dir, seq[0].replace(".png", ".xml")))
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
    else:
        start = b_idx

    # ---------- after ----------
    a_idx = int(STEP_RE.match(seq[-1]).group(1))
    ws = parse_widgets(os.path.join(app_dir, seq[-1].replace(".png", ".xml")))
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
    else:
        end = a_idx

    # ---------- 构造 full ----------
    full = [idx2png[i] for i in range(start, end + 1) if i in idx2png]
    if len(full) < 3:
        return None

    # ---------- grant：只收集系统权限 ----------
    sys = []
    for p in full[1:-1]:
        ws = parse_widgets(os.path.join(app_dir, p.replace(".png", ".xml")))
        if is_system_permission(ws):
            sig = permission_signature(ws)
            score = clarity_score(ws, os.path.join(app_dir, p))
            sys.append((p, sig, score))

    # ★ 最终闸门：0 个系统权限 → 删除
    if not sys:
        return None

    # ---------- 去重（改点1：重复默认保留“靠后”的） ----------
    # 策略：同 sig 出现多次时，直接覆盖为后出现的 p
    # 但如果你仍想用 clarity_score 选最清晰，可把“score比较”留着；
    # 这里按你的要求：重复默认保留靠后（时间顺序后出现的 step）
    best = {}
    for p, sig, score in sys:
        best[sig] = (p, score)  # ★ 后出现覆盖前出现

    # 保持 grant 的先后顺序：按 step index 排序（避免 dict 顺序受插入影响）
    def step_idx(name: str) -> int:
        m = STEP_RE.match(name)
        return int(m.group(1)) if m else -1

    grant = [v[0] for v in best.values()]
    grant.sort(key=step_idx)

    final = [full[0]] + grant + [full[-1]]
    if len(final) < 3:
        return None

    return final

# =========================================================
# Main（加进度条）
# =========================================================

def main():
    safe_mkdir(DST_ROOT)
    stat = defaultdict(int)

    apps = sorted(os.listdir(RAW_ROOT))
    app_pbar = tqdm(apps, desc="APKs", unit="apk")

    for app in app_pbar:
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
        out_app = os.path.join(DST_ROOT, app)
        safe_mkdir(out_app)

        result = []
        new_tp = []
        cid = 0

        chain_pbar = tqdm(raw, desc=f"{app} chains", unit="chain", leave=False)

        for seq in chain_pbar:
            stat["total"] += 1
            repaired = repair_chain(app_dir, steps, idx2png, seq)
            if repaired is None:
                stat["removed"] += 1
                continue

            stat["kept"] += 1
            item = {
                "chain_id": cid,
                "ui_before_grant": {"file": repaired[0], "feature": {"text": "", "widgets": []}},
                "ui_granting": [{"file": p, "feature": {"text": "", "widgets": []}} for p in repaired[1:-1]],
                "ui_after_grant": {"file": repaired[-1], "feature": {"text": "", "widgets": []}},
            }
            result.append(item)
            new_tp.append(repaired)

            imgs = [os.path.join(app_dir, p) for p in repaired]
            merge_images(imgs, os.path.join(out_app, f"chain_{cid}.png"))
            cid += 1

        if result:
            write_json(result, os.path.join(out_app, "result.json"))
            write_json(new_tp, os.path.join(out_app, "tupleOfPermissions.json"))

        app_pbar.set_postfix(
            kept=stat["kept"],
            removed=stat["removed"],
            total=stat["total"]
        )

    write_json(dict(stat), os.path.join(DST_ROOT, "summary.json"))
    print("DONE:", dict(stat))

if __name__ == "__main__":
    main()