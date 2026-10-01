"""실험 6: 아군 마을 전체를 정찰 화면으로 촬영하고, 마을회관 위치에 원을 그려 채점용으로 모은다.

전제: 아군 마을의 정찰 화면이 열린 상태.
실행:
  .venv\\Scripts\\python.exe experiments\\06_scout_town_hall.py              # 촬영 + 표시
  .venv\\Scripts\\python.exe experiments\\06_scout_town_hall.py --mark-only   # 촬영 없이 표시만 다시

- 촬영: 정찰 화면 하단 화살표로 넘어가며 촬영.
  ⚠️ 정찰 화면의 화살표는 끝에서 반대편으로 순환함 (전쟁 맵 패널과 다름). 회색이 되지 않으므로
  첫 촬영이 MAX_VILLAGES(50)장까지 갔음. 표시 단계에서 하단 순번(N/M)을 읽어 마을 번호로 정리하고 중복은 버림.
- 표시: API 키가 아직 없어 TH 레벨을 모르므로 모든 레벨을 매칭해 가장 높은 점수를 쓴다.
"""
import argparse
import re
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor import device, hud, town_hall  # noqa: E402

OUT = device.ROOT / "output" / "scout"
SHOTS = OUT / "shots"
REVIEW = OUT / "review"

SCOUT_PREV = (718, 975)
SCOUT_NEXT = (1190, 975)
MAX_VILLAGES = 50
PREV_TAP_WAIT = 0.2
NEXT_TAP_WAIT = 2.5  # 정찰 화면은 마을 전체를 새로 불러오므로 넉넉히


def _is_orange(img, center, r=25):
    x, y = center
    hsv = cv2.cvtColor(img[y - r:y + r, x - r:x + r], cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (5, 150, 180), (25, 255, 255)).mean() / 255 > 0.3


def capture():
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver = device.create_driver()
    try:
        img = device.screenshot(driver)
        if not (_is_orange(img, SCOUT_PREV) or _is_orange(img, SCOUT_NEXT)):
            print("정찰 화면이 아닌 것 같습니다 (하단 주황 화살표 없음). 종료.")
            return False
        t = time.perf_counter()
        for _ in range(MAX_VILLAGES - 1):
            device.tap(driver, *SCOUT_PREV)
            time.sleep(PREV_TAP_WAIT)
        time.sleep(NEXT_TAP_WAIT)
        print(f"1번 마을로 이동: {time.perf_counter() - t:.1f}s")

        t = time.perf_counter()
        for i in range(1, MAX_VILLAGES + 1):
            img = device.screenshot(driver)
            cv2.imwrite(str(SHOTS / f"{i:02d}.png"), img)
            if not _is_orange(img, SCOUT_NEXT):
                break
            device.tap(driver, *SCOUT_NEXT)
            time.sleep(NEXT_TAP_WAIT)
        print(f"촬영 {i}장: {time.perf_counter() - t:.1f}s")
        return True
    finally:
        driver.quit()


COUNTER_BOX = (870, 890, 1040, 940)  # 하단 "14/20" 순번


def read_counter(img) -> tuple[int, int] | None:
    x1, y1, x2, y2 = COUNTER_BOX
    r = hud.recognize(hud._white_text_mask(img[y1:y2, x1:x2]), fast=True)
    m = re.search(r"(\d+)\s*/\s*(\d+)", " ".join(r.txts or []))
    return (int(m.group(1)), int(m.group(2))) if m else None


def mark():
    if REVIEW.exists():
        shutil.rmtree(REVIEW)
    REVIEW.mkdir(parents=True)
    # 순번 OCR은 기지 배경과 겹쳐 자주 실패하므로, 한 장만 읽어 기준을 잡고 나머지는 촬영 순서로 계산
    paths = sorted(SHOTS.glob("[0-9][0-9].png"))
    for k, path in enumerate(paths):
        counter = read_counter(cv2.imread(str(path)))
        if counter and 1 <= counter[0] <= counter[1] <= MAX_VILLAGES:
            start = (counter[0] - k - 1) % counter[1]  # 0번째 스크린샷의 (번호 - 1)
            total = counter[1]
            print(f"기준: shot {path.stem} = {counter[0]}/{total}")
            break
    else:
        raise RuntimeError("순번을 한 장도 읽지 못함")
    by_number = {}
    for k, path in enumerate(paths[:total]):  # 화살표가 순환하므로 total장이면 전부
        by_number[(start + k) % total + 1] = (path, cv2.imread(str(path)))

    thumbs = []
    for number, (path, img) in sorted(by_number.items()):
        t = time.perf_counter()
        level, m = town_hall.locate_any(img)
        cx, cy = m.center
        radius = (m.box[2] - m.box[0]) // 2 + 10
        out = img.copy()
        cv2.circle(out, (cx, cy), radius, (0, 0, 255), 4)
        label = f"#{number} TH{level} {m.score:.2f}"
        cv2.putText(out, label, (cx - radius, cy - radius - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
        cv2.putText(out, label, (cx - radius, cy - radius - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        # 모음 이미지에서도 번호가 보이도록 좌상단에 크게
        cv2.putText(out, f"#{number}", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 12)
        cv2.putText(out, f"#{number}", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 4)
        cv2.imwrite(str(REVIEW / f"{number:02d}.png"), out)
        thumbs.append(cv2.resize(out, (640, 360)))
        print(f"#{number:<2} (shot {path.stem}): TH{level:<2} score={m.score:.3f} {m.template:16s} "
              f"center={m.center} {time.perf_counter() - t:.1f}s")

    # 한눈에 채점하기 위한 모음 (4열)
    cols = 4
    while len(thumbs) % cols:
        thumbs.append(np.zeros_like(thumbs[0]))
    rows = [np.hstack(thumbs[i:i + cols]) for i in range(0, len(thumbs), cols)]
    cv2.imwrite(str(OUT / "review_sheet.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("저장:", REVIEW, OUT / "review_sheet.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-only", action="store_true")
    args = parser.parse_args()
    if args.mark_only or capture():
        mark()
