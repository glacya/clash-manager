"""Appium 세션 생성과 기기 조작 (스크린샷, 탭)."""
import subprocess

import cv2
import numpy as np
from appium import webdriver
from appium.options.android import UiAutomator2Options

from . import layout
from .paths import ROOT

ADB = ROOT / "tools" / "android-sdk" / "platform-tools" / "adb.exe"

UDID = layout.get("device.udid")
PACKAGE = "com.supercell.clashofclans"
ACTIVITY = "com.supercell.titan.GameApp"


def create_driver(udid: str = UDID, system_port: int = 8200):
    opts = UiAutomator2Options()
    opts.udid = udid
    opts.system_port = system_port
    opts.no_reset = True
    opts.new_command_timeout = 300
    opts.set_capability("appium:appPackage", PACKAGE)
    opts.set_capability("appium:appActivity", ACTIVITY)
    opts.set_capability("appium:disableWindowAnimation", True)
    opts.set_capability("appium:ignoreHiddenApiPolicyError", True)
    driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)
    # 게임은 화면이 계속 움직여서 idle 대기를 끄지 않으면 동작마다 매우 느려짐
    driver.update_settings({"waitForIdleTimeout": 0})
    return driver


def screenshot(driver) -> np.ndarray:
    png = driver.get_screenshot_as_png()
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    layout.check_size(img)
    return img


def screenshot_adb(udid: str = UDID) -> np.ndarray:
    png = subprocess.run([str(ADB), "-s", udid, "exec-out", "screencap", "-p"],
                         capture_output=True, check=True).stdout
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    layout.check_size(img)
    return img


def tap(driver, x: int, y: int):
    driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
