import concurrent.futures
import itertools
import os
import json
import re
import traceback

import requests
from openai import OpenAI

import configs.config as config
import src.utils.utils as utils
from configs.config import CHAT_URL, DEFAULT_MODEL
from src.utils.utils import logger


def commit_to_deployed(prompt):
    """
    Send prompt to a locally deployed vLLM server using OpenAI-compatible API.
    Expected response format:
        {
            "choices": [
                {"message": {"content": "..."}}
            ]
        }
    """
    try:
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0,
            "max_tokens": 512
        }

        response = requests.post(
            CHAT_URL,
            json=payload,
            timeout=config.LLM_RESPONSE_TIMEOUT
        )
        response.raise_for_status()

        result = response.json()

        # NEW: 正确取出 vLLM / OpenAI Chat Completion 风格的输出
        return result["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        logger.error(f"LLM timeout! message:\n{prompt}")
        return None

    except Exception as e:
        logger.error(f"LLM request error: {e}")
        return None

def chat_api(prompt):
    os.environ["http_proxy"] = "http://localhost:7890"
    os.environ["https_proxy"] = "http://localhost:7890"

    client = OpenAI(
        api_key="sk-6LfO6o4V4skVM8dF59F51e0d225044D083869d63803b7047",
        base_url="https://api.xty.app/v1",
    )

    # completion = client.chat.completions.create(
    #     model="gpt-4o-mini",
    #     messages=messages,
    # )
    completion = client.completions.create(
        model="gpt-4o-mini",
        prompt=prompt,
    )

    assistant_message = completion.choices[0].message

    return assistant_message.content


class DataAnalyzeAgent:

    def __init__(self, path, analyze_scene=True, analyze_purpose=True, use_api=False, verbose=False):
        if os.path.dirname(path) == "":
            self.input_dir = os.path.join(config.DATA_PROCESSED_DIR, path)
        else:
            self.input_dir = path

        self._scene_classify_prompt = self._permission_necessity_prompt = self._purpose_analysis_prompt = (
            self._permission_usage_prompt
        ) = self._permissions_info_prompt = None

        self._load_assets()
        self._analyze_scene = analyze_scene
        self._analyze_purpose = analyze_purpose
        self.use_api = use_api
        self._conf_verbose = verbose
        self.allowed_map = self.permission_map["allowed_map"]
        self.banned_map = self.permission_map["banned_map"]
        self._skip_if_res_exist = False

    def _load_assets(self):
        with open(config.PROMPT_SCENE_CLASSIFY_PATH, "r", encoding="utf-8") as f:
            self._scene_classify_prompt = f.read()

        with open(config.PROMPT_PERMISSION_NECESSITY_PATH, "r", encoding="utf-8") as f:
            self._permission_necessity_prompt = f.read()

        with open(config.PROMPT_PURPOSE_TEXTS_PATH, "r", encoding="utf-8") as f:
            self._purpose_text_prompt = f.read()

        with open(config.PROMPT_PERMISSION_USAGE_PATH, "r", encoding="utf-8") as f:
            self._permission_usage_prompt = f.read()

        with open(config.PROMPT_PERMISSIONS_INFO_PATH, "r", encoding="utf-8") as f:
            self._permissions_info_prompt = f.read()

        with open(config.PERMISSION_MAP_PATH, "r", encoding="utf-8") as f:
            self.permission_map = json.load(f)

    def _scene_analysis(self, processed_data):
        for permission_request_info in processed_data:
            if not any(ui["permission"] for ui in permission_request_info["ui_granting"]):
                continue

            # TODO: 可以让大模型解释预定义场景的功能
            # scene classification
            ui_feature = json.dumps(
                {
                    "scenes": [
                        ui_granting["post_processed_feature"] for ui_granting in permission_request_info["ui_granting"]
                    ]
                    + [
                        permission_request_info["ui_after_grant"]["feature"],
                    ]
                },
                ensure_ascii=False,
            )
            # ui_feature = json.dumps({"scenes": [permission_request_info["processed_scene"]]}, ensure_ascii=False)
            scene_analysis = permission_request_info.get("scene_analysis", {})
            if (
                self._skip_if_res_exist
                and scene_analysis.get("analysis", [])
                and (scene_analysis.get("category", []) or scene_analysis.get("new_defined", []))
            ):
                logger.info("scene_analysis already exist, skip")
            else:
                combined_classify_res = self._scene_recognize(ui_feature)
                if combined_classify_res:
                    scene_analysis.update(combined_classify_res)
                else:
                    logger.warning("llm analyze failed")
                permission_request_info["scene_analysis"] = scene_analysis

            # permissions necessity
            if scene_analysis:
                compliance_analysis = permission_request_info.get("compliance_analysis", [])
                for granting_info in permission_request_info["ui_granting"]:
                    ui_feature = json.dumps(
                        {
                            "scenes": [
                                granting_info["post_processed_feature"],
                                permission_request_info["ui_after_grant"]["feature"],
                            ]
                        },
                        ensure_ascii=False,
                    )
                    permission = granting_info["permission"]
                    # if any(analysis["permission"] == permission for analysis in compliance_analysis):
                    #     continue

                    existing_compliance_analysis = next(
                        (
                            single_compliance_analysis
                            for single_compliance_analysis in compliance_analysis
                            if single_compliance_analysis["permission"] == permission
                        ),
                        None,
                    )
                    if existing_compliance_analysis:
                        scene_compliance = existing_compliance_analysis.setdefault("scene_compliance", {})
                    else:
                        scene_compliance = {}
                        compliance_analysis.append({"permission": permission, "scene_compliance": scene_compliance})

                    if self._skip_if_res_exist and scene_compliance:
                        logger.info("scene_compliance already exist, skip")
                        continue

                    if "READ_PHONE_STATE" in permission:
                        scene_compliance["permission_necessity"] = False
                        scene_compliance["description"] = "禁止获取IMEI"

                    else:
                        if scene_analysis["category"]:
                            # use scene-permissions map
                            categories = scene_analysis["category"]
                            if any(category not in self.allowed_map for category in scene_analysis["category"]):
                                scene_analysis["new_defined"].extend(
                                    [
                                        category
                                        for category in scene_analysis["category"]
                                        if category not in self.allowed_map
                                    ]
                                )
                            else:
                                banned_by_map = all(
                                    any(permission in self.banned_map[category] for permission in permission)
                                    for category in categories
                                )

                                # scene_analysis["permission_necessity"] = not banned_by_map
                                # scene_analysis["description"] = "根据场景权限映射表确定"

                                if banned_by_map:
                                    scene_compliance["permission_necessity"] = False
                                    scene_compliance["description"] = "根据场景权限映射表确定"

                                else:
                                    necessity_analysis = self._permission_judge(ui_feature, permission, categories)

                                    if necessity_analysis:
                                        scene_compliance.update(necessity_analysis)

                        if scene_analysis["new_defined"]:
                            # TODO: 可以在prompt中输入各权限可能存在的用途，辅助大模型判定
                            # use llm
                            categories = scene_analysis["new_defined"]

                            necessity_analysis = self._permission_judge(ui_feature, permission, categories)

                            if necessity_analysis:
                                scene_compliance.update(necessity_analysis)

            permission_request_info["compliance_analysis"] = compliance_analysis
        return processed_data

    def _permission_judge(self, ui_feature, permissions, categories):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(
                self._multi_try,
                itertools.repeat(
                    lambda: self._LLM_permission_necessity(ui_feature, permissions, categories),
                    times=config.PERMISSION_NECESSITY_TIMES,
                ),
                itertools.repeat(
                    ["permission_necessity", "description"],
                    times=config.PERMISSION_NECESSITY_TIMES,
                ),
            )

        t = f = 0
        t_des = []
        f_des = []
        for necessity_analyze_res in results:
            if necessity_analyze_res:
                if necessity_analyze_res["permission_necessity"]:
                    t += 1
                    t_des.append(necessity_analyze_res["description"])
                else:
                    f += 1
                    f_des.append(necessity_analyze_res["description"])
        necessity = t > f
        necessity_analysis = {
            "permission_necessity": necessity,
            "description": t_des if necessity else f_des,
        }
        return necessity_analysis

    def _scene_recognize(self, ui_feature):
        combined_classify_res = {"analysis": [], "category": set(), "new_defined": set()}

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(
                self._multi_try,
                itertools.repeat(lambda: self._LLM_scene_classify(ui_feature), times=config.SCENE_CLASSIFY_TIMES),
                itertools.repeat(["analysis", "category", "new_defined"], times=config.SCENE_CLASSIFY_TIMES),
            )

        for scene_classify_res in results:
            if scene_classify_res:
                combined_classify_res["analysis"].append(scene_classify_res["analysis"])
                combined_classify_res["category"].update(scene_classify_res["category"])
                if scene_classify_res["new_defined"]:
                    combined_classify_res["new_defined"].add(scene_classify_res["new_defined"])

        combined_classify_res["category"] = list(combined_classify_res["category"])
        combined_classify_res["new_defined"] = list(combined_classify_res["new_defined"])
        return combined_classify_res

    def _purpose_analysis(self, processed_data):
        for permission_request_info in processed_data:
            if not any(ui["permission"] for ui in permission_request_info["ui_granting"]):
                continue

            compliance_analysis = permission_request_info.setdefault("compliance_analysis", [])
            for ui_granting in permission_request_info["ui_granting"]:
                # feature = [permission_request_info["ui_before_grant"]["feature"]["text"]]
                # +[widget["text"] for widget in permission_request_info["ui_before_grant"]["feature"]["widgets"]]
                # +[ui_granting["post_processed_feature"]["text"]]
                # +[widget["text"] for widget in ui_granting["post_processed_feature"]["widgets"]]
                feature = []
                feature.append(permission_request_info["ui_before_grant"]["feature"]["text"])
                feature.extend(widget["text"] for widget in permission_request_info["ui_before_grant"]["feature"]["widgets"])
                feature.append(ui_granting["post_processed_feature"]["text"])
                feature.extend(widget["text"] for widget in ui_granting["post_processed_feature"]["widgets"])

                permission = ui_granting["permission"]

                existing_compliance_analysis = next(
                    (
                        single_compliance_analysis
                        for single_compliance_analysis in compliance_analysis
                        if single_compliance_analysis["permission"] == permission
                    ),
                    None,
                )
                if existing_compliance_analysis:
                    purpose_compliance = existing_compliance_analysis.setdefault("purpose_compliance", {})
                else:
                    purpose_compliance = {}
                    compliance_analysis.append({"permission": permission, "purpose_compliance": purpose_compliance})

                if self._skip_if_res_exist and purpose_compliance:
                    logger.info("purpose_compliance already exist, skip")
                    continue

                purpose_texts_res = self._multi_try(
                    lambda: self._LLM_purpose_text(feature, permission), keywords=["purpose_texts"]
                )
                if purpose_texts_res:
                    purpose_compliance.update(purpose_texts_res)

                if purpose_compliance.get("purpose_texts", []):
                    permission_usage_res = self._multi_try(
                        lambda: self._LLM_permission_usage(purpose_compliance.get("purpose_texts", []), permission),
                        keywords=["permission_usage_texts"],
                    )
                    if permission_usage_res:
                        purpose_compliance.update(permission_usage_res)
                else:
                    purpose_compliance["permission_usage_texts"] = []

        return processed_data

    def _load_processed_data(self):
        input = os.path.join(self.input_dir, "result.json")

        text_info = "[]"
        try:
            with open(input, "r", encoding="utf-8") as f:
                text_info = f.read()
        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")

        info_jobj = json.loads(text_info)
        return info_jobj

    def _LLM_scene_classify(self, feature):
        """
        scene analysis step 1: scene classify.
        """
        # messages = [
        #     {"role": "system", "content": self._scene_classify_prompt},
        #     {"role": "user", "content": feature},
        # ]
        prompt = self._scene_classify_prompt.replace("{feature}", str(feature))

        return self._to_LLM(prompt)

    def _LLM_permission_necessity(self, feature, permission, scene):
        """
        scene analysis step 2: check if the required permision is necessiry.
        """
        prompt = (
            self._permission_necessity_prompt.replace("{scene}", str(scene))
            .replace("{feature}", str(feature))
            .replace("{permission}", str(permission))
        )
        # messages = [{"role": "system", "content": self._permissions_info_prompt}, {"role": "user", "content": prompt}]

        return self._to_LLM(prompt)

    def _LLM_purpose_text(self, feature, permission):
        """
        purpose analysis step 1: extract purpose texts from raw texts.
        """
        prompt = self._purpose_text_prompt.replace("{feature}", str(feature)).replace("{permission}", str(permission))
        # messages = [{"role": "user", "content": prompt}]

        return self._to_LLM(prompt)

    def _LLM_permission_usage(self, texts, permission):
        """
        purpose analysis step 2: further extract texts which suggest the usage of permissions from purpose texts.
        """
        prompt = self._permissions_info_prompt + self._permission_usage_prompt.replace("{texts}", str(texts)).replace(
            "{permission}", str(permission)
        )
        # messages = [{"role": "system", "content": self._permissions_info_prompt}, {"role": "user", "content": prompt}]

        return self._to_LLM(prompt)

    def _to_LLM(self, prompt):
        if self.use_api:
            try:
                content = chat_api(prompt)
            except:
                content = None
        else:
            content = commit_to_deployed(prompt)
        return content

    def _parse_LLM_output(self, text):
        try:
            text = text.replace("，", ",")
            matches = re.findall(r"`{3}json(.*?)`", text, re.DOTALL)
            if matches:
                return json.loads(matches[-1])
        except:
            logger.error(f"[{self.input_dir}] parse LLM output failed: \n{text}")
            return None

    def _multi_try(self, func, keywords=None):
        if keywords is None:
            keywords = []

        res = None
        retry_times = 0
        while res is None and retry_times <= config.MAX_RETRY_TIMES:
            raw_res = func()
            if self._conf_verbose:
                print(raw_res)
            res = self._parse_LLM_output(raw_res)
            retry_times += 1

            if res is not None and not all(key in res.keys() for key in keywords):
                res = None

        return res

    def analyze_individually(self, imgs, re_ana=True):
        input_json_file = os.path.join(self.input_dir, "ps_results.json")

        with open(input_json_file, "r", encoding="utf-8") as f:
            scene_infos = json.load(f)

        for scene_info in scene_infos:
            if not re_ana:
                if scene_info.get("category", []) or scene_info.get("new_defined", []):
                    continue

            if scene_info["img"] not in imgs:
                continue

            # scene classification
            ui_feature = json.dumps(
                {"scenes": [scene_info["scene"]]},
                ensure_ascii=False,
            )
            # ui_feature = json.dumps({"scenes": [permission_request_info["processed_scene"]]}, ensure_ascii=False)
            combined_classify_res = self._scene_recognize(ui_feature)
            if combined_classify_res:
                scene_info.update(combined_classify_res)
            else:
                logger.warning("llm analyze failed")

        utils.dump_json(scene_infos, input_json_file)

    def run(self, skip_if_result_exist=False):
        logger.info(f"start analyze: {self.input_dir}")
        self._skip_if_res_exist = skip_if_result_exist

        processed_data = self._load_processed_data()
        if self._analyze_scene:
            processed_data = self._scene_analysis(processed_data)
        if self._analyze_purpose:
            processed_data = self._purpose_analysis(processed_data)
        output = os.path.join(self.input_dir, "result.json")
        utils.dump_json(processed_data, output)
        logger.info(f"already save analyze result to {output}")


def analyze_all():
    flag = False
    for path in os.listdir(config.DATA_PROCESSED_DIR):
        # if path == "fastbot-com.lhzjxf.cybzdq--running-minutes-15":
        #     flag = True
        # if os.path.isdir(os.path.join(config.DATA_PROCESSED_DIR, path)) and flag:
        #     logger.info(f"begin to analyze: {path}")
        #     DataAnalyzeAgent(path=path, analyze_scene=True, use_api=False).run()
        try:
            DataAnalyzeAgent(path=path, verbose=True, use_api=False, analyze_scene=False).run(skip_if_result_exist=False)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error("an error ocured!")
            traceback.print_exc()


if __name__ == "__main__":
    # path = "fastbot-cn.TuHu.android--running-minutes-15"
    # DataAnalyzeAgent(path, verbose=True).run(skip_if_result_exist=False)
    analyze_all()
