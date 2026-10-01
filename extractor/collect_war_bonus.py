"""클랜전 맵의 상대 마을 전체를 순회하며 전쟁 승리 보너스를 수집한다.

전제: 클랜전 맵에서 아무 상대 마을이나 선택해 하단 패널이 열린 상태.

실행:
  .venv\\Scripts\\python.exe -m extractor.collect_war_bonus              # 촬영 + 분석
  .venv\\Scripts\\python.exe -m extractor.collect_war_bonus --analyze <스크린샷 폴더>   # 분석만 다시

1) 촬영: 왼쪽 화살표를 49번 눌러 1번 마을로 간 뒤(마을은 최대 50개, 1번에서 멈춤),
   오른쪽 화살표를 누르며 스크린샷만 찍는다. 오른쪽 화살표가 회색이면 마지막 마을.
2) 분석: 1번 마을에서 보너스 숫자 위치를 한 번 찾고, 모든 스크린샷에서 그 영역만 잘라 인식.
   번호는 촬영 순서, 파워 = 골드 + 다크 엘릭서 × 150. (마을 이름은 공식 API로 얻음)

탭하는 것은 패널의 좌우 화살표뿐이며, 탭 전에 금지 영역(공격/정찰 버튼)과 겹치지 않는지 확인한다.
"""
import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path

import cv2

from . import device, hud, layout, war

MAX_VILLAGES = 50
PREV_TAP_WAIT = 0.15   # 1번으로 갈 때 연타 간격
NEXT_TAP_WAIT = 0.8    # 다음 마을 패널이 뜰 때까지 대기

OUT_DIR = device.ROOT / "output" / "war_bonus"


def _tap(driver, pos, wait):
    war.assert_safe(*pos)
    device.tap(driver, *pos)
    time.sleep(wait)


def capture(driver, shots_dir: Path) -> list[Path]:
    if not war.panel_open(device.screenshot(driver)):
        print("마을 패널이 열려 있지 않습니다. 클랜전 맵에서 상대 마을 하나를 선택한 뒤 다시 실행하세요.")
        return []

    t = time.perf_counter()
    for _ in range(MAX_VILLAGES - 1):
        _tap(driver, war.PREV_ARROW, PREV_TAP_WAIT)
    time.sleep(NEXT_TAP_WAIT)
    print(f"1번 마을로 이동: {time.perf_counter() - t:.1f}s")

    t = time.perf_counter()
    paths = []
    for i in range(1, MAX_VILLAGES + 1):
        img = device.screenshot(driver)
        path = shots_dir / f"{i:02d}.png"
        cv2.imwrite(str(path), img)
        paths.append(path)
        if not war.has_next(img):
            break
        _tap(driver, war.NEXT_ARROW, NEXT_TAP_WAIT)
    print(f"촬영 {len(paths)}장: {time.perf_counter() - t:.1f}s")
    return paths


def bonus_boxes(first_village_img, relocate: bool = False) -> war.BonusBoxes:
    """보너스 숫자 영역. config/layout.json에 저장된 값이 있으면 재사용, 없거나 relocate면 1번 마을에서 찾아 저장."""
    boxes = None if relocate else layout.learned(war.BONUS_BOXES_KEY)
    if boxes is None:
        boxes = war.locate_bonus_boxes(first_village_img)
        layout.learn(war.BONUS_BOXES_KEY, boxes)
        print(f"보너스 숫자 영역을 찾아 {layout.LAYOUT_PATH}에 저장: {boxes}")
    return boxes


def analyze(shots_dir: Path, relocate: bool = False) -> list[dict]:
    """번호는 촬영 순서(1번부터). 글자 위치는 1번 마을에서 한 번만 찾고(이후 캐시) 나머지는 같은 영역을 잘라 인식."""
    t = time.perf_counter()
    paths = sorted(shots_dir.glob("[0-9][0-9].png"))
    imgs = [cv2.imread(str(p)) for p in paths]
    boxes = bonus_boxes(imgs[0], relocate)
    rows = []
    for number, img in enumerate(imgs, start=1):
        bonus = war.read_bonus(img, boxes)
        values = {k: r.value for k, r in bonus.items()}
        rows.append({
            "number": number,
            **values,
            "power": war.power(values["gold"], values["dark_elixir"]),
            "ok": hud.is_confident(bonus),
        })
    print(f"분석 {len(rows)}장: {time.perf_counter() - t:.2f}s (영역 {boxes})")
    return rows


def save(rows: list[dict], shots_dir: Path):
    stamp = shots_dir.name
    with open(OUT_DIR / f"{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    (OUT_DIR / f"{stamp}.json").write_text(
        json.dumps({"collected_at": stamp, "villages": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"  {'번호':>4} {'골드':>10} {'엘릭서':>10} {'다크':>7} {'파워':>11}")
    for r in rows:
        mark = "" if r["ok"] else "  ← 확인 필요"
        print(f"  {r['number']:>4} {r['gold']!s:>10} {r['elixir']!s:>10} "
              f"{r['dark_elixir']!s:>7} {r['power']!s:>11}{mark}")
    print(f"저장: {OUT_DIR / (stamp + '.csv')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze", type=Path, help="이미 찍어 둔 스크린샷 폴더를 다시 분석")
    parser.add_argument("--relocate", action="store_true", help="저장된 보너스 숫자 영역을 무시하고 다시 찾기")
    args = parser.parse_args()

    if args.analyze:
        shots_dir = args.analyze.resolve()
    else:
        shots_dir = OUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        shots_dir.mkdir(parents=True, exist_ok=True)
        driver = device.create_driver()
        try:
            if not capture(driver, shots_dir):
                shots_dir.rmdir()
                return
        finally:
            driver.quit()

    save(analyze(shots_dir, args.relocate), shots_dir)


if __name__ == "__main__":
    main()
