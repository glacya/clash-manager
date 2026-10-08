"""클랜전 리그: 라운드별 아군·상대 파워 수집 (7일차에 한 번 실행해 1~7일차를 모두 수집하는 것이 목표).

전제: 리그전 지도 화면이 열려 있음 (패널이 열려 있어도 됨). Appium 서버 실행 중 (정찰 화면 축소에 사용).
실행: .venv\\Scripts\\python.exe -m extractor.collect_cwl [라운드 번호 ...]
  번호를 생략하면 API에서 state가 inWar/warEnded인 라운드 전부.
출력: output/cwl/<season>/round<N>/
  enemy/NN.png, enemy.csv  (상대: 전쟁 승리 보너스. 화면은 2배로 표기되므로 ÷2)
  ally/NN_th.png, NN_info.png, ally.csv  (아군: 정찰 → 마을회관 저장량, 일반 클랜전과 같은 방식)

라운드마다:
 1. 패널 닫기 → 하단 날짜 버튼 → 지도를 맨 위로 스와이프 (날짜마다 스크롤 위치가 달라 마을 좌표를 고정하기 위함)
 2. 상대 1번 마을 탭 → 패널 왼쪽 화살표 연타로 1번 확보 → 오른쪽 화살표로 넘기며 촬영 (회색이면 끝)
 3. 패널 닫기 → 아군 1번 마을 탭 → 1번 확보 → 초록 '정찰' 버튼 탭
    (정찰 버튼은 공격을 받았으면 왼쪽, 안 받았으면 가운데 → 색으로 찾음)
 4. 정찰 화면에서 아군 15개 마을을 collect_ally_loot와 같은 방식으로 처리 → '전쟁 지도'로 복귀
⚠️ 탭하는 곳: 날짜 버튼, 빈 곳, 마을, 패널 화살표, 정찰 버튼, 정찰 화면(건물·정보·닫기·화살표), 전쟁 지도 버튼뿐.
   상대 패널의 공격!/정찰, 준비일의 '멤버 변경'은 누르지 않음 (준비일 라운드는 처리하지 않음).
"""
import csv
import math
import sys
import time

import cv2
import numpy as np

from . import collect_ally_loot as cal, cwl, device, hud, layout, war

DAY_BUTTONS = {1: (580, 1030), 2: (708, 1030), 3: (836, 1030), 4: (963, 1030),  # 버튼 아래쪽: 탭 금지 영역(y≤1005) 회피
               5: (1092, 1030), 6: (1220, 1030), 7: (1348, 1030)}
BLANK = (250, 280)                  # 지도 왼쪽 위 나무 지대: 패널 닫기용
SWIPE_TOP = (960, 350, 960, 900)    # 가운데 돌길에서 아래로 끌어 지도를 맨 위로
ALLY_FIRST = (790, 700)             # 지도를 맨 위로 올렸을 때 아군 1번 마을
ENEMY_FIRST = (1120, 690)           # 상대 1번 마을
BONUS_COLUMN = (870, 865, 1008, 975)  # 리그전 상대 패널의 보너스 숫자 열 (일반 클랜전보다 오른쪽)
SCOUT_BUTTON_AREA = (640, 960, 1290, 1020)
WAR_MAP_BUTTON = layout.get("scout.war_map_button")
BONUS_MULTIPLIER = 2                # 리그전 화면은 전쟁 승리 보너스를 2배로 표기
MAX_VILLAGES = 15


def tap(x, y, wait=1.0):
    """전쟁 지도에서의 탭: 상대 패널의 공격!/정찰 버튼 영역이면 막음."""
    war.assert_safe(x, y)
    cal.tap(x, y, wait)


def scout_tap(x, y, wait=1.0):
    """정찰 화면 안에서의 탭 (공격 버튼이 없는 화면이라 지도용 금지 영역 검사를 하지 않음).
    정찰 화면 다음 화살표 (1190, 975)가 지도 패널의 금지 영역과 좌표가 겹치기 때문."""
    cal.tap(x, y, wait)


def to_map_top(day: int):
    tap(*BLANK, 1.0)
    tap(*DAY_BUTTONS[day], 4.0)
    for _ in range(3):
        cal.adb("shell", "input", "swipe", *map(str, SWIPE_TOP), "250")
        time.sleep(0.4)
    time.sleep(1.5)


def panel_open(img) -> bool:
    """리그전은 지도 위치에 따라 패널 위 주황 탭(^)이 안 보임 → 좌우 화살표 중 하나가 주황색이면 열린 것."""
    return war.has_next(img) or war._is_orange(img, war.PREV_ARROW, 25)


def open_first_in_panel(village: tuple[int, int]) -> bool:
    tap(*village, 2.0)
    if not panel_open(cal.shot()):
        return False
    for _ in range(MAX_VILLAGES - 1):
        tap(*war.PREV_ARROW, 0.15)
    time.sleep(0.8)
    return True


def collect_enemy(day: int, out) -> list[dict]:
    d = out / "enemy"
    d.mkdir(parents=True, exist_ok=True)
    if not open_first_in_panel(ENEMY_FIRST):
        raise RuntimeError(f"R{day}: 상대 패널이 열리지 않음")
    imgs = []
    for i in range(1, MAX_VILLAGES + 1):
        img = cal.shot()
        cv2.imwrite(str(d / f"{i:02d}.png"), img)
        imgs.append(img)
        if not war.has_next(img):
            break
        tap(*war.NEXT_ARROW, 0.8)
    boxes = war.locate_bonus_boxes(imgs[0], BONUS_COLUMN)
    rows = []
    for n, img in enumerate(imgs, start=1):
        bonus = war.read_bonus(img, boxes)
        v = {k: (r.value // BONUS_MULTIPLIER if r.value is not None else None) for k, r in bonus.items()}
        rows.append({"number": n, **v, "power": war.power(v["gold"], v["dark_elixir"]),
                     "ok": hud.is_confident(bonus)})
    _write(out / "enemy.csv", rows)
    return rows


def find_scout_button(img) -> tuple[int, int] | None:
    x1, y1, x2, y2 = SCOUT_BUTTON_AREA
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 120, 120), (85, 255, 255))
    ys, xs = np.nonzero(mask)
    if len(xs) < 500:
        return None
    return int(xs.mean()) + x1, int(ys.mean()) + y1


def collect_ally(driver, day: int, members: list[dict], out) -> list[dict]:
    d = out / "ally"
    d.mkdir(parents=True, exist_ok=True)
    tap(*BLANK, 1.0)
    if not open_first_in_panel(ALLY_FIRST):
        raise RuntimeError(f"R{day}: 아군 패널이 열리지 않음")
    scout = find_scout_button(cal.shot())
    if scout is None:
        raise RuntimeError(f"R{day}: 정찰 버튼을 찾지 못함")
    tap(*scout, 5.0)
    rows = []
    for i, m in enumerate(members):
        number = i + 1
        t = time.perf_counter()
        r = cal.process_village(driver, number, m["townhallLevel"], d)
        s = r["storage"] or {}
        rows.append({"number": number, "name": m["name"], "th": m["townhallLevel"],
                     "gold_stored": s.get("gold"), "dark_stored": s.get("dark_elixir"),
                     "gold_loot": math.floor(s["gold"] * cal.LOOT_FACTOR) if "gold" in s else None,
                     "dark_loot": math.floor(s["dark_elixir"] * cal.LOOT_FACTOR) if "dark_elixir" in s else None,
                     "found": r["found"]})
        print(f"  아군 #{number:<2} TH{m['townhallLevel']:<2} {m['name']:<10} found={r['found']} "
              f"gold={rows[-1]['gold_stored']} dark={rows[-1]['dark_stored']} {time.perf_counter() - t:.1f}s", flush=True)
        if number < len(members):
            scout_tap(*cal.SCOUT_NEXT, 3.0)
    scout_tap(*WAR_MAP_BUTTON, 6.0)
    _write(out / "ally.csv", rows)
    return rows


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def main():
    group, wars = cwl.fetch()
    print(cwl.summary(wars))
    rounds = [int(a) for a in sys.argv[1:]] or [n for n, w in sorted(wars.items()) if w["state"] in cwl.PLAYED_STATES]
    base = cwl.season_dir(group["season"])
    driver = device.create_driver()
    try:
        for day in rounds:
            w = wars[day]
            if w["state"] not in cwl.PLAYED_STATES:
                print(f"R{day}: state={w['state']} → 건너뜀")
                continue
            out = base / f"round{day}"
            t = time.perf_counter()
            print(f"R{day} vs {w['opponent']['name']}", flush=True)
            to_map_top(day)
            enemy = collect_enemy(day, out)
            print(f"  상대 {len(enemy)}개, 신뢰도 낮음 {sum(not r['ok'] for r in enemy)}개", flush=True)
            to_map_top(day)
            members = sorted(w["clan"]["members"], key=lambda m: m["mapPosition"])
            ally = collect_ally(driver, day, members, out)
            print(f"  아군 {len(ally)}개, 실패 {sum(not r['found'] for r in ally)}개, {time.perf_counter() - t:.0f}s", flush=True)
    finally:
        driver.quit()
    print("저장:", base)


if __name__ == "__main__":
    main()
