"""실험 2: 마을 화면 재화 OCR 후, 성공 시 클랜전 버튼 탭.

클랜전 버튼은 좌측 하단 '공격!' 버튼 위 두 버튼 중 위쪽 (교차된 검 아이콘).
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor import device, hud  # noqa: E402

OUT = device.ROOT / "output" / "02"
CLAN_WAR_BUTTON = (65, 728)  # 1920x1080 기준


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    driver = device.create_driver()
    try:
        img = device.screenshot(driver)
        cv2.imwrite(str(OUT / "village.png"), img)

        t = time.perf_counter()
        readings = hud.read_resources(img)
        print(f"OCR {time.perf_counter() - t:.2f}s")
        for name, r in readings.items():
            print(f"  {name:12s} {r.value!s:>12}  text={r.text!r} score={r.score:.2f}")

        if not hud.is_confident(readings):
            print("OCR 실패 또는 신뢰도 부족 → 클랜전 버튼을 누르지 않고 종료")
            return

        print(f"클랜전 버튼 탭 {CLAN_WAR_BUTTON}")
        device.tap(driver, *CLAN_WAR_BUTTON)
        time.sleep(4)
        cv2.imwrite(str(OUT / "after_clan_war_tap.png"), device.screenshot(driver))
        print("저장:", OUT / "after_clan_war_tap.png")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
