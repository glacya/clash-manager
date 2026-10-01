"""실험 5-2: 정찰 화면 하단 오른쪽 화살표를 한 번 눌러 다음 마을로 넘어가는지 확인."""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor import device  # noqa: E402

OUT = device.ROOT / "output" / "04"
SCOUT_NEXT = (1190, 975)

d = device.create_driver()
try:
    device.tap(d, *SCOUT_NEXT)
    time.sleep(3)
    img = device.screenshot(d)
    cv2.imwrite(str(OUT / "scout_next.png"), img)
    print("saved")
finally:
    d.quit()
