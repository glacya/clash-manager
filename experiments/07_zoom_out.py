"""실험 7-1: 정찰 화면에서 핀치로 최대한 축소."""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor import device  # noqa: E402

d = device.create_driver()
try:
    for i in range(3):
        d.execute_script("mobile: pinchCloseGesture", {
            "left": 300, "top": 100, "width": 1320, "height": 780, "percent": 0.9, "speed": 2500})
        time.sleep(0.5)
    time.sleep(1)
    cv2.imwrite(str(device.ROOT / "output" / "agent" / "zoomed_out.png"), device.screenshot(d))
    print("saved")
finally:
    d.quit()
