#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule-only UI baseline for binary permission risk classification.

Per app input (preferred):
  - ocr.json
  - widgets.json
  - permission.json

Fallback input:
  - result.json
  - result_permission.json

Per app output:
  - result_rule_only_keyword.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from tqdm import tqdm


DEFAULT_OUT = "result_rule_only_keyword.json"
DEFAULT_APP_PREFIX = ""


PERMISSION_KEYWORDS = {
    # LOCATION
    "ACCESS_FINE_LOCATION": [
        "location", "nearby", "near", "distance", "around", "map", "maps", "navigation",
        "gps", "route", "directions", "local", "near me", "city", "region", "area",
        "weather", "forecast", "check in", "ride", "taxi", "delivery", "food nearby",
        "store nearby", "restaurant nearby", "travel", "trip", "tracking", "position",
        "locate", "find nearby", "nearby users", "discover nearby", "around you",
    ],
    "ACCESS_COARSE_LOCATION": [
        "location", "nearby", "map", "maps", "local", "city", "area", "weather",
        "near me", "around", "discover nearby", "nearby users", "region",
        "local services", "local news", "recommend nearby", "find nearby",
    ],
    "ACCESS_BACKGROUND_LOCATION": [
        "location tracking", "background location", "always allow location",
        "route tracking", "fitness tracking", "activity tracking", "travel log",
        "running route", "movement tracking",
    ],
    # CAMERA
    "CAMERA": [
        "camera", "take photo", "take picture", "capture", "scan", "qr",
        "qr code", "barcode", "scan code", "document scan", "scan document",
        "take selfie", "video call", "video chat", "face verification",
        "face login", "face recognition", "photo upload", "shoot video",
        "record video", "profile photo", "avatar", "camera preview",
        "live streaming", "broadcast", "ar camera", "filter camera",
    ],
    # MICROPHONE
    "RECORD_AUDIO": [
        "microphone", "mic", "record audio", "voice", "voice message",
        "voice chat", "voice call", "audio record", "speech", "speech input",
        "voice search", "talk", "speak", "audio message", "sound recording",
        "voice recognition", "speech recognition", "karaoke", "sing",
        "music record", "voice assistant",
    ],
    # STORAGE
    "READ_EXTERNAL_STORAGE": [
        "save file", "load file", "open file", "read file", "import",
        "download", "upload", "gallery", "photo library", "media library",
        "open image", "open video", "choose photo", "select image",
        "attach file", "view files", "browse files", "file manager",
        "backup", "restore", "media access",
    ],
    "WRITE_EXTERNAL_STORAGE": [
        "save photo", "save video", "save file", "download file",
        "export", "export file", "store data", "write file",
        "save recording", "save screenshot", "save media",
        "cache file", "save document",
    ],
    "MANAGE_EXTERNAL_STORAGE": [
        "file manager", "manage files", "clean storage",
        "storage manager", "delete files", "scan storage",
        "storage cleanup", "storage optimization",
    ],
    # CONTACTS
    "READ_CONTACTS": [
        "contacts", "friends", "find friends", "invite friends",
        "contact list", "address book", "sync contacts",
        "import contacts", "discover friends", "match contacts",
        "people you may know", "connect contacts",
    ],
    "WRITE_CONTACTS": [
        "add contact", "edit contact", "save contact",
        "create contact", "update contact", "manage contacts",
    ],
    "GET_ACCOUNTS": [
        "account", "google account", "sync account",
        "login account", "user account", "profile account",
    ],
    # PHONE
    "READ_PHONE_STATE": [
        "device id", "phone status", "call status", "phone info",
        "sim info", "network info", "identify device",
    ],
    "CALL_PHONE": [
        "make call", "phone call", "dial", "call support",
        "call contact", "call service",
    ],
    "READ_CALL_LOG": [
        "call history", "call log", "recent calls",
    ],
    "WRITE_CALL_LOG": [
        "manage call log", "save call record",
    ],
    # SMS
    "READ_SMS": [
        "sms", "text message", "verification code",
        "read message", "otp", "receive code",
        "login code", "security code",
    ],
    "SEND_SMS": [
        "send sms", "send message", "invite via sms",
        "text verification",
    ],
    "RECEIVE_SMS": [
        "receive sms", "receive verification",
        "auto detect code", "auto fill code",
    ],
    # CALENDAR
    "READ_CALENDAR": [
        "calendar", "events", "schedule", "agenda",
        "view events", "calendar sync", "event reminder",
    ],
    "WRITE_CALENDAR": [
        "add event", "create event", "edit calendar",
        "save event", "schedule meeting", "add reminder",
    ],
    # SENSORS
    "BODY_SENSORS": [
        "heart rate", "fitness tracking", "health data",
        "body sensor", "activity tracking", "exercise tracking",
    ],
    "ACTIVITY_RECOGNITION": [
        "step counter", "fitness", "walking", "running",
        "activity tracking", "motion tracking",
    ],
    # BLUETOOTH / NEARBY
    "BLUETOOTH_CONNECT": [
        "connect device", "bluetooth device", "pair device",
        "connect headphones", "connect speaker",
        "connect wearable", "connect watch",
    ],
    "BLUETOOTH_SCAN": [
        "scan device", "discover device", "find nearby device",
        "nearby device", "bluetooth scan",
    ],
    # WIFI / NETWORK
    "ACCESS_WIFI_STATE": [
        "wifi", "wifi network", "connect wifi",
        "wifi status", "wifi scan", "available networks",
    ],
    "CHANGE_WIFI_STATE": [
        "enable wifi", "disable wifi", "manage wifi",
        "wifi connection",
    ],
    # MEDIA
    "READ_MEDIA_IMAGES": [
        "view photos", "image gallery", "select photos",
        "upload photo", "choose picture",
    ],
    "READ_MEDIA_VIDEO": [
        "play video", "select video", "upload video",
        "video library",
    ],
    "READ_MEDIA_AUDIO": [
        "music library", "audio library", "play music",
        "select audio", "record music",
    ],
}


ZH_ALIAS_HINTS = {
    "ACCESS_FINE_LOCATION": ["位置", "定位", "附近", "地图", "导航", "天气", "同城"],
    "ACCESS_COARSE_LOCATION": ["位置", "定位", "附近", "地图", "同城"],
    "CAMERA": ["相机", "拍照", "拍摄", "扫码", "二维码", "头像"],
    "RECORD_AUDIO": ["麦克风", "录音", "语音", "说话", "唱歌", "K歌"],
    "READ_EXTERNAL_STORAGE": ["文件", "相册", "图片", "导入", "读取", "恢复", "下载"],
    "WRITE_EXTERNAL_STORAGE": ["保存", "导出", "写入", "下载", "文件", "缓存"],
    "MANAGE_EXTERNAL_STORAGE": ["文件管理", "清理", "存储", "删除", "扫描"],
    "READ_CONTACTS": ["通讯录", "联系人", "好友"],
    "READ_SMS": ["短信", "验证码"],
    "ACCESS_WIFI_STATE": ["wifi", "网络", "热点"],
}


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def uniq_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for s in items:
        t = str(s).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def normalize_permission_name(s: str) -> str:
    s = str(s or "").strip().upper()
    s = re.sub(r"\s+", "_", s)
    return s


def parse_chain_id(item: Dict[str, Any], default_idx: int) -> int:
    raw = item.get("chain_id", default_idx)
    try:
        return int(raw)
    except Exception:
        return default_idx


def find_app_dirs(target: str, app_prefix: str, app: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    if not os.path.isdir(target):
        return []
    if app:
        p = os.path.join(target, app)
        return [p] if os.path.isdir(p) else []
    out: List[str] = []
    for d in sorted(os.listdir(target)):
        p = os.path.join(target, d)
        if not os.path.isdir(p):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        out.append(p)
    return out


def _texts_from_value(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        out: List[str] = []
        for x in v:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for k in ("text", "label", "title", "name"):
                    if isinstance(x.get(k), str):
                        out.append(x[k])
        return out
    if isinstance(v, dict):
        out: List[str] = []
        for k in ("text", "label", "title", "name"):
            if isinstance(v.get(k), str):
                out.append(v[k])
        return out
    return []


def _parse_chain_list(obj: Any) -> List[Tuple[int, Dict[str, Any]]]:
    pairs: List[Tuple[int, Dict[str, Any]]] = []
    if isinstance(obj, list):
        for i, raw in enumerate(obj):
            item = as_dict(raw)
            if not item:
                continue
            pairs.append((parse_chain_id(item, i), item))
        return pairs
    if isinstance(obj, dict):
        chains = obj.get("chains")
        if isinstance(chains, list):
            for i, raw in enumerate(chains):
                item = as_dict(raw)
                if not item:
                    continue
                pairs.append((parse_chain_id(item, i), item))
            return pairs
    return pairs


def _collect_from_result_json(app_dir: str) -> Tuple[Dict[int, str], Dict[int, str]]:
    ocr_map: Dict[int, str] = {}
    widget_map: Dict[int, str] = {}
    path = os.path.join(app_dir, "result.json")
    data = load_json(path)
    if not isinstance(data, list):
        return ocr_map, widget_map

    for i, raw in enumerate(data):
        item = as_dict(raw)
        if not item:
            continue
        cid = parse_chain_id(item, i)
        ocr_texts: List[str] = []
        widget_texts: List[str] = []
        stages: List[Dict[str, Any]] = []
        stages.append(as_dict(item.get("ui_before_grant")))
        for g in as_list(item.get("ui_granting")):
            stages.append(as_dict(g))
        stages.append(as_dict(item.get("ui_after_grant")))

        for st in stages:
            feat = as_dict(st.get("feature"))
            txt = feat.get("text")
            if isinstance(txt, str):
                ocr_texts.append(txt)
            for w in as_list(feat.get("widgets")):
                wd = as_dict(w)
                if isinstance(wd.get("text"), str):
                    widget_texts.append(wd["text"])

        ocr_map[cid] = " | ".join(uniq_keep_order(ocr_texts))
        widget_map[cid] = " | ".join(uniq_keep_order(widget_texts))
    return ocr_map, widget_map


def load_ocr_map(app_dir: str) -> Dict[int, str]:
    path = os.path.join(app_dir, "ocr.json")
    if not os.path.exists(path):
        return _collect_from_result_json(app_dir)[0]
    out: Dict[int, str] = {}
    for cid, item in _parse_chain_list(load_json(path)):
        texts: List[str] = []
        for k in ("ocr_text", "text", "ocr", "before_text", "granting_text", "after_text", "content"):
            texts.extend(_texts_from_value(item.get(k)))
        out[cid] = " | ".join(uniq_keep_order(texts))
    return out


def load_widget_map(app_dir: str) -> Dict[int, str]:
    path = os.path.join(app_dir, "widgets.json")
    if not os.path.exists(path):
        return _collect_from_result_json(app_dir)[1]
    out: Dict[int, str] = {}
    for cid, item in _parse_chain_list(load_json(path)):
        texts: List[str] = []
        for k in ("widget_text", "widget_texts", "widgets", "texts"):
            texts.extend(_texts_from_value(item.get(k)))
        out[cid] = " | ".join(uniq_keep_order(texts))
    return out


def load_permission_map(app_dir: str) -> Dict[int, List[str]]:
    out: Dict[int, List[str]] = {}
    for filename in ("permission.json", "result_permission.json"):
        path = os.path.join(app_dir, filename)
        if not os.path.exists(path):
            continue
        for i, raw in enumerate(as_list(load_json(path))):
            item = as_dict(raw)
            if not item:
                continue
            cid = parse_chain_id(item, i)
            perms: List[str] = out.get(cid, [])

            for key in ("permission", "requested_permission"):
                if isinstance(item.get(key), str):
                    perms.append(normalize_permission_name(item[key]))
            for key in ("permissions", "requested_permissions", "predicted_permissions"):
                val = item.get(key)
                if isinstance(val, list):
                    for x in val:
                        if isinstance(x, str):
                            perms.append(normalize_permission_name(x))
                elif isinstance(val, str):
                    perms.append(normalize_permission_name(val))

            evt = as_dict(item.get("permission_event"))
            if isinstance(evt.get("permissions"), list):
                for x in evt["permissions"]:
                    if isinstance(x, str):
                        perms.append(normalize_permission_name(x))

            out[cid] = uniq_keep_order(perms)
    return out


def clip_text(s: str, max_chars: int) -> str:
    s = str(s or "").strip()
    return s[:max_chars] if len(s) > max_chars else s


def match_permission(permission: str, text: str) -> Tuple[bool, str]:
    p = normalize_permission_name(permission)
    keywords = [k.lower() for k in PERMISSION_KEYWORDS.get(p, [])]
    zh_hints = ZH_ALIAS_HINTS.get(p, [])
    t = text.lower()

    for kw in keywords:
        if kw and kw in t:
            return True, kw
    for kw in zh_hints:
        if kw and kw in text:
            return True, kw
    return False, ""


def infer_chain(ocr_text: str, widget_text: str, permissions: List[str]) -> Dict[str, Any]:
    text_blob = f"{ocr_text}\n{widget_text}".strip()
    if not permissions:
        return {
            "pred": "risky",
            "reason": "missing_permission",
            "permission_judgements": [],
        }

    judgements: List[Dict[str, Any]] = []
    all_ok = True
    for p in permissions:
        ok, hit = match_permission(p, text_blob)
        if not ok:
            all_ok = False
        judgements.append({
            "permission": p,
            "matched": ok,
            "matched_keyword": hit,
        })

    return {
        "pred": "safe" if all_ok else "risky",
        "reason": "all_permissions_matched" if all_ok else "permission_not_matched",
        "permission_judgements": judgements,
    }


def run_one_app(app_dir: str, out_name: str, force: bool) -> int:
    out_path = os.path.join(app_dir, out_name)
    if (not force) and os.path.exists(out_path):
        data = load_json(out_path)
        n = len(data) if isinstance(data, list) else 0
        print(f"[SKIP] app={os.path.basename(app_dir)} output exists ({n}): {out_name}")
        return n

    ocr_map = load_ocr_map(app_dir)
    widget_map = load_widget_map(app_dir)
    perm_map = load_permission_map(app_dir)
    chain_ids = sorted(set(ocr_map.keys()) | set(widget_map.keys()) | set(perm_map.keys()))
    if not chain_ids:
        print(f"[WARN] app={os.path.basename(app_dir)} no chain data found")
        dump_json(out_path, [])
        return 0

    rows: List[Dict[str, Any]] = []
    for cid in tqdm(chain_ids, desc=f"RuleOnly {os.path.basename(app_dir)}", leave=False):
        ocr_text = clip_text(ocr_map.get(cid, ""), 5000)
        widget_text = clip_text(widget_map.get(cid, ""), 3000)
        perms = perm_map.get(cid, [])
        result = infer_chain(ocr_text=ocr_text, widget_text=widget_text, permissions=perms)
        rows.append({
            "chain_id": int(cid),
            "pred": result["pred"],
            "reason": result["reason"],
            "permissions": perms,
            "permission_judgements": result["permission_judgements"],
        })

    rows.sort(key=lambda x: int(x["chain_id"]))
    dump_json(out_path, rows)
    print(f"[DONE] app={os.path.basename(app_dir)} chains={len(rows)} file={out_path}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-only binary baseline with permission keyword dictionary")
    parser.add_argument("target", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--out", default=DEFAULT_OUT, help="output filename in each app folder")
    parser.add_argument("--app-prefix", default=DEFAULT_APP_PREFIX)
    parser.add_argument("--app", default="", help="run a single app dir name under processed root")
    parser.add_argument("--force", action="store_true", help="overwrite existing output")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    app_dirs = find_app_dirs(target=target, app_prefix=args.app_prefix, app=args.app)
    if not app_dirs:
        raise SystemExit(f"no app dirs found: {target}")

    total = 0
    for app_dir in app_dirs:
        try:
            total += run_one_app(app_dir=app_dir, out_name=args.out, force=args.force)
        except Exception as exc:
            print(f"[WARN] app failed: {app_dir} err={exc}")

    print(f"\n[SUMMARY] apps={len(app_dirs)} chains={total} out={args.out}")


if __name__ == "__main__":
    main()
