import json
import os
from PIL import Image
import cv2
import pytesseract
import unicodedata
import re
from xml.etree import ElementTree
import hashlib

import utils
import config
from utils import logger
import numpy as np


# ===============================
#      OCR + WIDGETS 优化
# ===============================

IMPORTANT_CLASSES = {
    "android.widget.TextView",
    "android.widget.Button",
    "android.widget.ImageButton",
    "android.widget.CheckedTextView",
    "android.widget.EditText",
}

KEYWORDS = [
    "允许", "拒绝", "位置", "定位", "存储", "电话",
    "相机", "麦克风", "录音", "联系人", "同意",
    "取消", "权限", "授权", "访问", "使用", "开启", "确认"
]


# ===============================
#      Chain Fingerprint
# ===============================

def _normalize_text(t: str) -> str:
    t = re.sub(r"\s+", "", t or "")
    return t.lower()


def compute_chain_fingerprint(item) -> str:
    before = item["ui_before_grant"]["feature"].get("text", "")
    grant = ""
    if item.get("ui_granting"):
        grant = item["ui_granting"][0]["feature"].get("text", "")
    after = item["ui_after_grant"]["feature"].get("text", "")
    key = "|".join([
        _normalize_text(before),
        _normalize_text(grant),
        _normalize_text(after)
    ])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ===============================
#      Chain 拼接工具
# ===============================

def merge_images_horizontally(img_paths, output_path):
    imgs = []
    for p in img_paths:
        if os.path.exists(p):
            try:
                imgs.append(Image.open(p).convert("RGB"))
            except Exception:
                pass

    if not imgs:
        logger.warning(f"Skip empty chain image: {output_path}")
        return

    min_h = min(im.height for im in imgs)
    resized = [
        im.resize((int(im.width * min_h / im.height), min_h))
        for im in imgs
    ]

    total_width = sum(im.width for im in resized)
    merged = Image.new("RGB", (total_width, min_h), (255, 255, 255))

    x = 0
    for im in resized:
        merged.paste(im, (x, 0))
        x += im.width

    merged.save(output_path)


# ===============================
#      DataProcessAgent
# ===============================

class DataProcessAgent:
    NORMAL = 0
    PROCESS = 1
    COMBINE = 2

    def __init__(self, path, ocr_type=PROCESS, output_path=None):
        self.input_dir = os.path.abspath(path)
        folder_name = os.path.basename(self.input_dir)

        if output_path is None:
            self.output_dir = os.path.join(config.DATA_PROCESSED_DIR, folder_name)
        else:
            self.output_dir = os.path.join(output_path, folder_name)

        self._ocr_type = ocr_type

    # ===============================
    #          OCR
    # ===============================

    def _ocr_preprocess(self, image_path):
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

    def _clean_ocr_text(self, text):
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9，。？！：:+-]", "", text)
        return text.replace(" ", "").strip()

    def _ocr_image_enhanced(self, image_path):
        bin_img = self._ocr_preprocess(image_path)
        if bin_img is None:
            return ""

        results = []
        for scale in [1.0, 1.3, 1.6, 2.0]:
            resized = cv2.resize(bin_img, None, fx=scale, fy=scale)
            text = pytesseract.image_to_string(
                Image.fromarray(resized), "chi_sim"
            )
            results.append(text)

        return self._clean_ocr_text("\n".join(results))

    def _ocr_image(self, image_path):
        try:
            text = pytesseract.image_to_string(
                Image.open(image_path), "chi_sim"
            )
            return self._clean_ocr_text(text)
        except Exception:
            return ""

    # ===============================
    #         XML widgets
    # ===============================

    def _score_widget(self, w):
        score = 0
        if w.get("text"):
            score += 2
            if any(k in w["text"] for k in KEYWORDS):
                score += 4
        if "permission" in w.get("resource-id", ""):
            score += 6
        if w.get("class") in IMPORTANT_CLASSES:
            score += 2
        score += w.get("depth", 0) * 0.3
        return score

    def _widgets_from_xml(self, xml_path):
        if not os.path.exists(xml_path):
            return []

        try:
            root = ElementTree.fromstring(
                open(xml_path, encoding="utf-8").read()
            )
        except Exception:
            return []

        widgets = []

        def dfs(node, depth=0):
            widgets.append({
                "text": node.attrib.get("text", ""),
                "class": node.attrib.get("class", ""),
                "resource-id": node.attrib.get("resource-id", ""),
                "depth": depth
            })
            for c in node:
                dfs(c, depth + 1)

        dfs(root)
        widgets.sort(key=self._score_widget, reverse=True)
        return widgets[:20]

    # ===============================
    #           Phase2 主逻辑
    # ===============================

    def _text_from_raw_data(self):
        tuple_file = os.path.join(self.input_dir, "tupleOfPermissions.json")
        if not os.path.exists(tuple_file):
            return []

        utils.cp_file(
            tuple_file,
            os.path.join(self.output_dir, "tupleOfPermissions.json")
        )

        raw_list = json.load(open(tuple_file, encoding="utf-8"))
        processed = []

        for cid, seq in enumerate(raw_list):
            item = {
                "chain_id": cid,
                "chain_fingerprint": None,
                "ui_before_grant": None,
                "ui_granting": [],
                "ui_after_grant": None
            }

            for i, img_name in enumerate(seq):
                img_path = os.path.join(self.input_dir, img_name)
                xml_path = img_path.replace(".png", ".xml")

                text = (
                    self._ocr_image(img_path)
                    if self._ocr_type == self.NORMAL
                    else self._ocr_image_enhanced(img_path)
                )

                entry = {
                    "feature": {
                        "text": text,
                        "widgets": self._widgets_from_xml(xml_path)
                    },
                    "file": img_name
                }

                if i == 0:
                    item["ui_before_grant"] = entry
                elif i == len(seq) - 1:
                    item["ui_after_grant"] = entry
                else:
                    item["ui_granting"].append(entry)

                utils.cp_file(img_path, os.path.join(self.output_dir, img_name))
                utils.cp_file(
                    xml_path,
                    os.path.join(self.output_dir, img_name.replace(".png", ".xml"))
                )

            item["chain_fingerprint"] = compute_chain_fingerprint(item)
            processed.append(item)

        return processed

    # ===============================
    #              run
    # ===============================

    def run(self, skip_if_result_exist=False):
        result_file = os.path.join(self.output_dir, "result.json")

        if skip_if_result_exist and os.path.exists(result_file):
            logger.info(f"Skip existing result: {self.output_dir}")
            return

        utils.delete_directory(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        data = self._text_from_raw_data()
        utils.dump_json(data, result_file)

        # ⭐ 自动生成 chain 拼接截图
        for item in data:
            cid = item["chain_id"]
            out_img = os.path.join(self.output_dir, f"chain_{cid}.png")
            if os.path.exists(out_img):
                continue

            paths = []
            paths.append(os.path.join(self.output_dir, item["ui_before_grant"]["file"]))
            for g in item.get("ui_granting", []):
                paths.append(os.path.join(self.output_dir, g["file"]))
            paths.append(os.path.join(self.output_dir, item["ui_after_grant"]["file"]))

            try:
                merge_images_horizontally(paths, out_img)
            except Exception as e:
                logger.warning(f"Fail chain {cid}: {e}")

        logger.info(
            f"Phase2 done: {self.input_dir}, chains={len(data)}"
        )