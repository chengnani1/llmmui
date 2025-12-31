import shutil
import traceback
from apkutils2 import APK
import time
import os
import concurrent.futures
import adbutils

import config
import utils
from utils import logger


class DataCollectAgent:

    def __init__(
        self, apk_path=None, package=None, time=config.TIME_LIMIT, throttle=config.THROTTLE, output_dir=None
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

        self.fastbot_output_dir = config.FASTBOT_OUTPUT.format(package=self._package, time=self._time)

        if output_dir is None:
            self.output_dir = config.DATA_RAW_DIR
        else:
            self.output_dir = output_dir

    def get_package(self):
        return self._package

    def _clear_res(self):
        command = ["adb", "shell", "rm", "-rf", f"{config.ANDROID_DATA_DIR}/{self.fastbot_output_dir}/"]
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
        self._device.uninstall(self._package)

    def _run_GUI_test(self):
        command = [
            "adb",
            "shell",
            config.FASTBOT_COMMAND.format(package=self._package, time=self._time, throttle=self._throttle),
        ]
        utils.exec(command)

    def _pull_result(self):
        android_data_dir = config.ANDROID_DATA_DIR + "/" + self.fastbot_output_dir + "/"
        utils.delete_directory(os.path.join(self.output_dir, self.fastbot_output_dir))
        os.makedirs(self.output_dir, exist_ok=True)

        command = ["adb", "pull", android_data_dir, self.output_dir]
        utils.exec(command)

    def run(self, skip_if_result_exist=False):
        if skip_if_result_exist:
            result_path = os.path.join(self.output_dir, self.fastbot_output_dir)
            if os.path.exists(result_path):
                logger.debug(f"{result_path} : already exists")
                return

        self._clear_res()
        self._uninstall_package()

        time.sleep(1)

        self._install_apk()

        try:
            self._run_GUI_test()
        except KeyboardInterrupt:
            pass
        finally:
            time.sleep(1)
            self._pull_result()

        time.sleep(1)
        self._clear_res()
        self._uninstall_package()


if __name__ == "__main__":
    #root = r""
    for path in utils.list_apk_file_path(root):
        try:
            agent = DataCollectAgent(path).run(skip_if_result_exist=True)
        except KeyboardInterrupt:
            raise
        except:
            traceback.print_exc()
            pass
