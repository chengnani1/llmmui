import traceback
from apkutils2 import APK
import time
import os
import concurrent.futures
import adbutils
import src.utils.utils as utils
from src.utils.utils import logger

from configs import settings

FASTBOT_COMMAND = (
    "CLASSPATH=/sdcard/monkeyq.jar:/sdcard/framework.jar:/sdcard/fastbot-thirdpart.jar "
    "exec app_process /system/bin com.android.commands.monkey.Monkey "
    "-p {package} --agent reuseq --running-minutes {time} --throttle {throttle} -v -v"
)
DEFAULT_THROTTLE = settings.FASTBOT_THROTTLE


class DataCollectAgent:

    def __init__(
        self, apk_path=None, package=None, time=settings.TIME_LIMIT, throttle=DEFAULT_THROTTLE, output_dir=None
    ) -> None:
        self._adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
        self._device = self._adb.device()

        self._time = time
        self._apk_path = apk_path
        self._throttle = throttle

        if package:
            self._package = package
        else:
            apk = APK(self._apk_path)
            self._package = apk.get_manifest()["@package"]

        self.fastbot_output_dir = settings.FASTBOT_OUTPUT_TEMPLATE.format(
            package=self._package,
            time=self._time,
        )

        if output_dir is None:
            self.output_dir = settings.DATA_RAW_DIR
        else:
            self.output_dir = output_dir

    def get_package(self):
        return self._package

    def _has_usable_result(self, result_path: str) -> bool:
        if not os.path.isdir(result_path):
            return False
        tuple_path = os.path.join(result_path, "tupleOfPermissions.json")
        return os.path.exists(tuple_path)

    def _clear_res(self):
        command = ["adb", "shell", "rm", "-rf", f"{settings.ANDROID_DATA_DIR}/{self.fastbot_output_dir}/"]
        utils.exec(command)

    def _install_apk(self):
        def install_task():
            self._device.install(self._apk_path)

        # install_task()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                executor.submit(install_task).result(timeout=180)
            except concurrent.futures.TimeoutError:
                logger.error(f"install apk timeout! : {self._apk_path}")
                raise

    def _uninstall_package(self):
        try:
            self._device.uninstall(self._package)
        except Exception as exc:
            logger.debug("uninstall skipped/failed for %s: %s", self._package, exc)

    def _run_GUI_test(self):
        timeout_seconds = settings.FASTBOT_COMMAND_TIMEOUT_SECONDS
        if timeout_seconds <= 0:
            timeout_seconds = self._time * 60 + settings.FASTBOT_TIMEOUT_BUFFER_SECONDS
        command = [
            "adb",
            "shell",
            FASTBOT_COMMAND.format(package=self._package, time=self._time, throttle=self._throttle),
        ]
        utils.exec(command, timeout=timeout_seconds)

    def _pull_result(self):
        android_data_dir = settings.ANDROID_DATA_DIR + "/" + self.fastbot_output_dir + "/"
        utils.delete_directory(os.path.join(self.output_dir, self.fastbot_output_dir))
        os.makedirs(self.output_dir, exist_ok=True)

        command = ["adb", "pull", android_data_dir, self.output_dir]
        utils.exec(command, timeout=settings.ADB_PULL_TIMEOUT_SECONDS)

    def run(self, skip_if_result_exist=False):
        if skip_if_result_exist:
            result_path = os.path.join(self.output_dir, self.fastbot_output_dir)
            if self._has_usable_result(result_path):
                logger.debug(f"{result_path} : already exists")
                return "skipped_existing"

        self._clear_res()
        self._uninstall_package()

        time.sleep(1)

        self._install_apk()
        fastbot_error = None

        try:
            self._run_GUI_test()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            # Fastbot occasionally exits non-zero even when partial/full outputs were produced.
            # We keep pulling results and only fail hard if no output is recovered.
            fastbot_error = exc
            logger.error("fastbot run failed for %s: %s", self._package, exc)
        finally:
            try:
                time.sleep(1)
                self._pull_result()
            except Exception as pull_exc:
                logger.error("pull result failed for %s: %s", self._package, pull_exc)
                if fastbot_error is None:
                    raise
                raise RuntimeError(f"fastbot failed and pull failed: {pull_exc}") from fastbot_error

        time.sleep(1)
        self._clear_res()
        self._uninstall_package()

        if fastbot_error is not None:
            result_path = os.path.join(self.output_dir, self.fastbot_output_dir)
            if self._has_usable_result(result_path):
                logger.warning(
                    "fastbot returned non-zero but output exists, continue: %s",
                    result_path,
                )
                return "recovered_with_output"
            raise RuntimeError(f"fastbot failed and no output recovered: {fastbot_error}") from fastbot_error
        return "success"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase1 data collect (fastbot/adb)")
    parser.add_argument("target", nargs="?", help="APK path or directory containing APKs")
    args = parser.parse_args()

    target = args.target
    if not target:
        raise SystemExit("Missing target. Use: python data_collect.py /path/to/apk_or_dir")

    if os.path.isdir(target):
        for path in utils.list_apk_file_path(target):
            try:
                DataCollectAgent(path).run(skip_if_result_exist=True)
            except KeyboardInterrupt:
                raise
            except Exception:
                traceback.print_exc()
    else:
        try:
            DataCollectAgent(target).run(skip_if_result_exist=True)
        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
