import json
import os
from PIL import Image
import cv2
import pytesseract
import unicodedata
import re
from xml.etree import ElementTree

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

KEYWORDS = ["允许", "拒绝", "位置", "定位", "存储", "电话", "相机", "麦克风", "录音",
            "联系人", "同意", "取消", "权限", "授权", "访问", "使用", "开启", "确认"]


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
    #          OCR 预处理
    # ===============================
    def _ocr_preprocess(self, image_path):

        img = cv2.imread(image_path)
        if img is None:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # gamma 校正
        gamma = 1.5
        table = ((np.arange(256) / 255.0) ** (1 / gamma) * 255).astype("uint8")
        gray = cv2.LUT(gray, table)

        # 中值滤波
        gray = cv2.medianBlur(gray, 3)

        # 自适应阈值
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            31, 5
        )

        return binary

    def _clean_ocr_text(self, text):

        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9，。？！：:+-]", "", text)
        text = text.replace(" ", "")
        lines = text.split("\n")
        text = "\n".join(dict.fromkeys(lines))

        return text.strip()

    def _ocr_image_enhanced(self, image_path):

        bin_img = self._ocr_preprocess(image_path)
        if bin_img is None:
            return ""

        results = []
        scales = [1.0, 1.3, 1.6, 2.0]

        for scale in scales:
            resized = cv2.resize(bin_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            pil_img = Image.fromarray(resized)
            text = pytesseract.image_to_string(pil_img, "chi_sim")
            results.append(text)

        merged_text = "\n".join(results)
        return self._clean_ocr_text(merged_text)

    def _ocr_image(self, image_path):
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, "chi_sim")
            return self._clean_ocr_text(text)
        except:
            return ""

    # ===============================
    #         XML widgets 优化
    # ===============================

    def _score_widget(self, w):

        score = 0
        text = w.get("text", "")
        rid = w.get("resource-id", "")
        cls = w.get("class", "")

        if text:
            score += 2
            if len(text) > 4:
                score += 1
            if any(k in text for k in KEYWORDS):
                score += 4

        if "permission_group_title" in rid:
            score += 16
        
        if "permission" in rid:
            score += 6

        if cls in IMPORTANT_CLASSES:
            score += 2

        score += w.get("depth", 0) * 0.3
        return score

    def _widgets_from_xml(self, xml_path):

        if not os.path.exists(xml_path):
            return []

        try:
            xml_str = open(xml_path, "r", encoding="utf-8").read()
            root = ElementTree.fromstring(xml_str)
        except:
            return []

        widgets = []

        def dfs(node, depth=0, parent=None):
            text = node.attrib.get("text", "")
            cls = node.attrib.get("class", "")
            rid = node.attrib.get("resource-id", "").split("/")[-1]

            if cls in IMPORTANT_CLASSES or text:
                widgets.append({
                    "text": text,
                    "class": cls,
                    "resource-id": rid,
                    "parent_text": parent.attrib.get("text", "") if parent else "",
                    "depth": depth,
                })

            for child in node:
                dfs(child, depth + 1, parent=node)

        dfs(root)

        widgets = sorted(widgets, key=self._score_widget, reverse=True)

        high_important = [w for w in widgets if self._score_widget(w) >= 6]
        final_widgets = high_important + widgets[:15]

        seen = set()
        uniq = []
        for w in final_widgets:
            sig = (w["text"], w["class"], w["resource-id"])
            if sig not in seen:
                uniq.append(w)
                seen.add(sig)

        return uniq[:20]

    # ===============================
    #           Phase2 主逻辑
    # ===============================

    def _text_from_raw_data(self):

        tuple_file = os.path.join(self.input_dir, "tupleOfPermissions.json")
        if not os.path.exists(tuple_file):
            return []

        utils.cp_file(tuple_file, os.path.join(self.output_dir, "tupleOfPermissions.json"))

        raw_list = json.load(open(tuple_file, "r"))
        processed_list = []

        # -------------------------------
        # ⭐ 给每条链加入 chain_id
        # -------------------------------
        for cid, seq in enumerate(raw_list):

            item = {
                "chain_id": cid,
                "ui_before_grant": None,
                "ui_granting": [],
                "ui_after_grant": None
            }

            for i, img_name in enumerate(seq):
                img_path = os.path.join(self.input_dir, img_name)
                xml_path = img_path.replace(".png", ".xml")

                if self._ocr_type == self.NORMAL:
                    text = self._ocr_image(img_path)
                else:
                    text = self._ocr_image_enhanced(img_path)

                widgets = self._widgets_from_xml(xml_path)

                if i == 0:
                    item["ui_before_grant"] = {
                        "feature": {"text": text, "widgets": widgets},
                        "file": img_name
                    }
                elif i == len(seq) - 1:
                    item["ui_after_grant"] = {
                        "feature": {"text": text, "widgets": widgets},
                        "file": img_name
                    }
                else:
                    item["ui_granting"].append({
                        "feature": {"text": text, "widgets": widgets},
                        "raw_text": text,
                        "file": img_name
                    })

                utils.cp_file(img_path, os.path.join(self.output_dir, img_name))
                utils.cp_file(xml_path, os.path.join(self.output_dir, img_name.replace(".png", ".xml")))

            processed_list.append(item)

        return processed_list

    def run(self, skip_if_result_exist=False):
        result_file = os.path.join(self.output_dir, "result.json")

        if skip_if_result_exist and os.path.exists(result_file):
            return

        utils.delete_directory(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        processed = self._text_from_raw_data()
        utils.dump_json(processed, result_file)