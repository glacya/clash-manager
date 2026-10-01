"""실험 1: Appium 세션 생성, 스크린샷 취득, UI 계층 노출 여부 확인.

Clash of Clans를 실행한 상태에서 다음을 확인합니다.
- UiAutomator2 세션이 Google Play Games 개발자 에뮬레이터에 붙는지
- 스크린샷 속도 (Appium vs adb screencap)
- 게임 화면이 UiAutomator2 요소로 노출되는지 (page_source)
"""
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from appium import webdriver
from appium.options.android import UiAutomator2Options

UDID = "localhost:6520"
PACKAGE = "com.supercell.clashofclans"
ACTIVITY = "com.supercell.titan.GameApp"
OUT = Path(__file__).resolve().parent.parent / "output" / "01"
ADB = Path(__file__).resolve().parent.parent / "tools" / "android-sdk" / "platform-tools" / "adb.exe"


def create_driver():
    opts = UiAutomator2Options()
    opts.udid = UDID
    opts.system_port = 8200
    opts.no_reset = True
    opts.new_command_timeout = 300
    opts.set_capability("appium:appPackage", PACKAGE)
    opts.set_capability("appium:appActivity", ACTIVITY)
    opts.set_capability("appium:disableWindowAnimation", True)
    opts.set_capability("appium:ignoreHiddenApiPolicyError", True)
    driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)
    driver.update_settings({"waitForIdleTimeout": 0})
    return driver


def screenshot_appium(driver) -> np.ndarray:
    png = driver.get_screenshot_as_png()
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


def screenshot_adb() -> np.ndarray:
    png = subprocess.run([str(ADB), "-s", UDID, "exec-out", "screencap", "-p"],
                         capture_output=True, check=True).stdout
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


def timed(fn, n=5):
    times = []
    for _ in range(n):
        t = time.perf_counter()
        img = fn()
        times.append(time.perf_counter() - t)
    return img, sum(times) / n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    driver = create_driver()
    print(f"session created in {time.perf_counter() - t:.1f}s")
    try:
        print("current activity:", driver.current_activity)
        print("window size:", driver.get_window_size())
        time.sleep(15)  # 게임 로딩 대기

        img, avg = timed(lambda: screenshot_appium(driver))
        cv2.imwrite(str(OUT / "appium.png"), img)
        print(f"appium screenshot: {img.shape[1]}x{img.shape[0]}, avg {avg * 1000:.0f} ms")

        img, avg = timed(screenshot_adb)
        cv2.imwrite(str(OUT / "adb.png"), img)
        print(f"adb screenshot:    {img.shape[1]}x{img.shape[0]}, avg {avg * 1000:.0f} ms")

        source = driver.page_source
        (OUT / "page_source.xml").write_text(source, encoding="utf-8")
        print(f"page_source: {len(source)} chars, {source.count('<android.')} android nodes")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
