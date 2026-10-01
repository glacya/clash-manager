"""아군 마을 전체를 정찰하며 마을회관 저장 자원으로 전리품과 파워를 계산한다.

전제: 아군 마을의 정찰 화면이 열린 상태. TH 레벨은 공식 API(currentwar)에서 읽는다.
실행: .venv\\Scripts\\python.exe -m extractor.collect_ally_loot [--war <currentwar.json>] [--start N] [번호 ...]

마을마다 (사용자 제공 절차):
 1. 핀치로 최대한 축소.
 2. TH 레벨 템플릿으로 TH 후보 위치를 찾음 (4x4 건물).
 3. 후보를 탭 → 하단 버튼으로 판정: "정보" 하나 = 건물, "정보"+"스킨 보기" = 영웅(다시 시도), 없음 = 다시 시도.
 4. "정보" → 제목이 "마을회관"인지 이미지 템플릿으로 확인 (RapidOCR는 한글 미지원).
    TH 무기(기가 인페르노 등)가 먼저 나오면 정보 창 하단 화살표로 전환 (좌표 미확인 → 스크린샷 남기고 건너뜀).
 5. 저장된 골드/엘릭서/다크 엘릭서 판독.
 6. 전리품 = floor(저장량 × 87.5 / 2), 파워 = 골드 전리품 + 다크 엘릭서 전리품 × 150.
다음 마을은 정찰 화면 하단 오른쪽 화살표 (끝에서 순환함).
"""
import argparse
import csv
import math
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import api, device, hud, layout, town_hall, war

UDID = device.UDID
# 좌표는 config/layout.json (scout, info 항목)
SCOUT_NEXT = layout.get("scout.next_arrow")
INFO_SINGLE = layout.get("scout.info_button")          # 건물 선택 시 "정보" 버튼
BUILDING_ICON = layout.get("scout.selected_building_icon")
HERO_ICON = layout.get("scout.selected_hero_icon")     # 영웅 선택 시 "정보" (옆에 "스킨 보기")
PINCH_AREA = layout.get("scout.pinch_area")             # (left, top, width, height)
INFO_CLOSE = layout.get("info.close_button")
INFO_WEAPON_ARROW = layout.get("info.weapon_arrow")    # TH 무기 정보 ↔ 마을회관 정보 전환 (파란 화살표)
STORAGE_PANEL = layout.get("info.storage_panel")
TITLE_STRIP = layout.get("info.title_strip")
TITLE_TH = cv2.imread(str(device.ROOT / "assets" / "ui" / "title_town_hall.png"))
LOOT_FACTOR = 87.5 / 2  # 전리품 = floor(저장량 × 87.5 / 2)
# 후보 중심에서 조금씩 옮겨 가며 다시 누를 위치 (영웅/벽 회피)
TAP_OFFSETS = [(0, 5), (-15, 15), (15, 15), (0, 25), (-25, 0), (25, 0), (0, -10)]

OUT_DIR = device.ROOT / "output" / "ally_loot"


def adb(*args) -> bytes:
    return subprocess.run([str(device.ADB), "-s", UDID, *args], capture_output=True, check=True).stdout


def shot() -> np.ndarray:
    return device.screenshot_adb(UDID)


def tap(x, y, wait=1.2):
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(wait)


def _blue_ratio(img, c, r=22):
    x, y = c
    hsv = cv2.cvtColor(img[y - r:y + r, x - r:x + r], cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (95, 120, 120), (125, 255, 255)).mean() / 255


def selection(img) -> str:
    """'building' | 'hero' | 'none'"""
    if _blue_ratio(img, BUILDING_ICON) > 0.3:
        return "building"
    if _blue_ratio(img, HERO_ICON) > 0.3:
        return "hero"
    return "none"


def is_town_hall_title(img) -> bool:
    x1, y1, x2, y2 = TITLE_STRIP
    res = cv2.matchTemplate(img[y1:y2, x1:x2], TITLE_TH, cv2.TM_CCOEFF_NORMED)
    return res.max() > 0.8


def read_storage(img) -> dict | None:
    """정보 창의 '저장 용량: a/b' 칸들. 읽는 순서대로 골드, 엘릭서, 그리고 최대치가 가장 작은 것이 다크 엘릭서."""
    x1, y1, x2, y2 = STORAGE_PANEL
    r = hud.recognize(img[y1:y2, x1:x2])
    if not r.txts:
        return None
    items = []
    for box, txt in zip(r.boxes, r.txts):
        m = re.fullmatch(r"\s*(\d[\d\s]*)/(\d[\d\s]*)\s*", txt)
        if m:
            cy = sum(p[1] for p in box) / 4
            cx = sum(p[0] for p in box) / 4
            items.append((round(cy / 40), cx, int(m.group(1).replace(" ", "")), int(m.group(2).replace(" ", ""))))
    if len(items) < 3:
        return None
    items.sort()
    dark = min(items, key=lambda i: i[3])
    rest = [i for i in items if i is not dark]
    return {"gold": rest[0][2], "gold_max": rest[0][3], "elixir": rest[1][2], "elixir_max": rest[1][3],
            "dark_elixir": dark[2], "dark_elixir_max": dark[3]}


def zoom_out(driver):
    for _ in range(2):
        left, top, width, height = PINCH_AREA
        driver.execute_script("mobile: pinchCloseGesture", {
            "left": left, "top": top, "width": width, "height": height, "percent": 0.9, "speed": 2500})
        time.sleep(0.4)
    time.sleep(0.8)


def open_town_hall_info() -> np.ndarray | None:
    """'정보'를 누르고 제목이 마을회관이 될 때까지 무기 화살표로 전환. 마을회관이 아니면 None (창은 닫음)."""
    tap(*INFO_SINGLE, wait=1.8)
    info = shot()
    for _ in range(2):
        if is_town_hall_title(info):
            return info
        # TH 무기(인페르노 포탑 등) 정보가 먼저 뜨면 오른쪽 아래 파란 화살표로 마을회관 정보로 전환
        if _blue_ratio(info, INFO_WEAPON_ARROW, 25) < 0.3:
            break
        tap(*INFO_WEAPON_ARROW, wait=1.5)
        info = shot()
    tap(*INFO_CLOSE, wait=1.2)
    return None


def process_village(driver, number: int, th_level: int, out: Path) -> dict:
    zoom_out(driver)
    base = shot()
    cands = town_hall.candidates(base, th_level, k=3)
    log = []
    for ci, m in enumerate(cands):
        cx, cy = m.center
        # 1순위 후보는 여러 위치로, 나머지 후보는 몇 군데만 시도
        for dx, dy in (TAP_OFFSETS if ci == 0 else TAP_OFFSETS[:3]):
            x, y = cx + dx, cy + dy
            tap(x, y)
            sel = selection(shot())
            log.append(f"c{ci}tap({x},{y})={sel}")
            if sel != "building":  # 영웅이 눌렸거나 아무것도 선택 안 됨 → 위치를 옮겨 다시
                continue
            info = open_town_hall_info()
            if info is None:
                log.append("not-TH")
                continue
            result = _finish(number, th_level, base, info, x, y, out)
            result.update({"template_score": m.score, "log": log})
            return result
    cv2.imwrite(str(out / f"{number:02d}_failed.png"), base)
    return {"found": False, "storage": None, "log": log}


def _finish(number, th_level, base, info, x, y, out) -> dict:
    """저장량 판독, 정보 창 닫기, TH에 원을 그린 이미지 저장."""
    storage = read_storage(info)
    cv2.imwrite(str(out / f"{number:02d}_info.png"), info)
    tap(*INFO_CLOSE, wait=1.2)
    marked = base.copy()
    label = f"#{number} TH{th_level}"
    cv2.circle(marked, (x, y), 45, (0, 0, 255), 4)
    cv2.putText(marked, label, (x - 60, y - 58), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
    cv2.putText(marked, label, (x - 60, y - 58), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.imwrite(str(out / f"{number:02d}_th.png"), marked)
    return {"found": True, "tap": (x, y), "storage": storage}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--war", help="currentwar JSON 파일 (생략하면 API에서 받음)")
    parser.add_argument("--start", type=int, default=1, help="현재 열려 있는 정찰 화면의 마을 번호")
    parser.add_argument("only", nargs="*", type=int, help="이 번호의 마을만 처리")
    args = parser.parse_args()
    war_json = api.load_war(args.war)
    members = sorted(war_json["clan"]["members"], key=lambda mb: mb["mapPosition"])
    start = args.start
    only = set(args.only)
    # 정찰 화살표는 순환하므로 시작 번호부터 한 바퀴
    order = list(range(start - 1, len(members))) + list(range(0, start - 1))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / stamp
    out.mkdir(parents=True, exist_ok=True)

    driver = device.create_driver()
    rows = []
    try:
        remaining = set(only) if only else set(range(1, len(members) + 1))
        for step, i in enumerate(order):
            mb = members[i]
            number = i + 1
            if not only or number in only:
                t = time.perf_counter()
                r = process_village(driver, number, mb["townhallLevel"], out)
                s = r["storage"] or {}
                gold_loot = math.floor(s["gold"] * LOOT_FACTOR) if "gold" in s else None
                dark_loot = math.floor(s["dark_elixir"] * LOOT_FACTOR) if "dark_elixir" in s else None
                row = {"number": number, "name": mb["name"], "th": mb["townhallLevel"],
                       "gold_stored": s.get("gold"), "dark_stored": s.get("dark_elixir"),
                       "gold_loot": gold_loot, "dark_loot": dark_loot,
                       "power": war.power(gold_loot, dark_loot), "found": r["found"]}
                rows.append(row)
                print(f"#{number:<2} TH{row['th']:<2} {row['name']:<10} found={r['found']} "
                      f"gold={row['gold_stored']} dark={row['dark_stored']} power={row['power']} "
                      f"{time.perf_counter() - t:.1f}s | {' '.join(r['log'])}", flush=True)
            remaining.discard(number)
            if not remaining or step == len(order) - 1:
                break
            tap(*SCOUT_NEXT, wait=3.0)
    finally:
        driver.quit()

    if rows:
        with open(OUT_DIR / f"{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    print("저장:", out, OUT_DIR / f"{stamp}.csv")


if __name__ == "__main__":
    main()
