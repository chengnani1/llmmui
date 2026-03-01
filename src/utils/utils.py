import sys
import logging
import subprocess
import os
import shutil
import json
import time
from contextlib import contextmanager

from configs import settings


logging.basicConfig(
    level=logging.DEBUG,
    format=f"[run_id={settings.RUN_ID}] [%(asctime)s - %(name)s - %(levelname)s] - %(message)s",
)
logger = logging.getLogger("yama")


def delete_directory(directory):
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info(f"Deleted directory: {directory}")
        else:
            logger.info(f"Directory {directory} does not exist.")
    except Exception as e:
        logger.error(f"Error: {e}")


def delete_file(file):
    try:
        if os.path.exists(file):
            os.remove(file)
            logger.info(f"Deleted file: {file}")
        else:
            logger.info(f"file {file} does not exist.")
    except Exception as e:
        logger.error(f"Error: {e}")


def exec(command, capture_result=False, capcure_result=False, timeout=None):
    want_capture = bool(capture_result or capcure_result)
    try:
        if want_capture:
            return subprocess.run(
                command,
                text=True,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,
            )
        else:
            return subprocess.run(
                command,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True,
                check=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,
            )
    except subprocess.CalledProcessError as exc:
        logger.error("Command failed: %s", command)
        if exc.stderr:
            logger.error("stderr: %s", str(exc.stderr).strip())
        raise
    except UnicodeDecodeError:
        logger.error("Unicode decode error while running command: %s", command)
        raise


def dump_json(jobj, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    res = json.dumps(jobj, ensure_ascii=False)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(res)


def cp_file(src_file_path, dst_file_path):
    os.makedirs(os.path.dirname(dst_file_path), exist_ok=True)
    try:
        shutil.copy(src_file_path, dst_file_path)
    except FileNotFoundError:
        logger.error("Error source file ")
    except Exception as e:
        logger.error(f"Error while copy file：{e}")


def list_apk_file_path(root_dir):
    """
    list all apk file path recursively
    """
    res = []
    for sub_dir in os.listdir(root_dir):
        path = os.path.join(root_dir, sub_dir)
        if sub_dir.endswith(".apk"):
            res.append(path)
        elif os.path.isdir(path):
            res.extend(list_apk_file_path(path))
    return res


@contextmanager
def time_the_block(path):
    start_time = time.time()
    yield
    end_time = time.time()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{str(end_time - start_time)}\n")
