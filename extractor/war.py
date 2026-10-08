"""클랜전 맵에서 상대 마을을 선택했을 때 나오는 하단 패널 판독과 이동.

좌표는 1920x1080 기준, config/layout.json의 war 항목.
마을 번호와 이름은 공식 API로 얻으므로 판독하지 않는다. 필요한 것은 전쟁 승리 보너스뿐.
⚠️ 패널의 '공격!' 버튼과 '정찰' 버튼은 절대 탭하지 않는다 (FORBIDDEN_BOXES).
"""
import cv2
import numpy as np

from . import hud, layout

BonusBoxes = dict[str, tuple[int, int, int, int]]  # (x1, y1, x2, y2)

# 보너스 숫자 열 전체 (아이콘 제외). 이 안에서 1번 마을 기준으로 글자 위치를 한 번 찾는다.
BONUS_COLUMN = layout.get("war.bonus_column")
BONUS_KEYS = ("gold", "elixir", "dark_elixir")
BONUS_BOXES_KEY = "war.bonus_boxes"  # 찾아낸 숫자 위치를 layout.learned에 저장할 때의 키
DARK_ELIXIR_WEIGHT = 150

PREV_ARROW = layout.get("war.prev_arrow")
NEXT_ARROW = layout.get("war.next_arrow")
PANEL_TAB = layout.get("war.panel_tab")  # 패널 위 주황색 탭(^)의 왼쪽 부분
FORBIDDEN_BOXES = layout.get("war.forbidden_boxes")  # 공격!, 정찰


def power(gold: int | None, dark_elixir: int | None) -> int | None:
    if gold is None or dark_elixir is None:
        return None
    return gold + dark_elixir * DARK_ELIXIR_WEIGHT


def locate_bonus_boxes(img: np.ndarray, column: tuple[int, int, int, int] | None = None) -> BonusBoxes:
    """패널에서 골드/엘릭서/다크 엘릭서 숫자 영역을 찾는다 (글자 위치 탐지, 한 번만 실행).

    숫자는 아이콘 쪽으로 오른쪽 정렬이므로, 오른쪽 끝이 열의 오른쪽에 붙은 영역만 쓰고
    자릿수가 달라도 들어가도록 세 줄의 왼쪽 끝을 가장 넓은 줄에 맞춘다.
    """
    x1, y1, x2, y2 = column or BONUS_COLUMN
    scale, pad = 2, 40  # hud._white_text_mask의 확대 배율과 여백
    result = hud.detect(hud._white_text_mask(img[y1:y2, x1:x2]))
    rects = []
    for b in result.boxes if result.boxes is not None else []:
        xs = [(p[0] - pad) / scale + x1 for p in b]
        ys = [(p[1] - pad) / scale + y1 for p in b]
        if max(xs) > x2 - 30:
            rects.append((min(xs), min(ys), max(xs), max(ys)))
    if len(rects) != len(BONUS_KEYS):
        raise RuntimeError(f"보너스 숫자 영역을 {len(BONUS_KEYS)}개 찾지 못함: {rects}")
    rects.sort(key=lambda r: r[1])
    left = int(min(r[0] for r in rects)) - 25
    right = int(max(r[2] for r in rects)) + 4
    return {k: (left, int(r[1]) - 3, right, int(r[3]) + 3) for k, r in zip(BONUS_KEYS, rects)}


def read_bonus(img: np.ndarray, boxes: BonusBoxes) -> dict[str, hud.Reading]:
    # 영역이 정해져 있으므로 인식만(fast) 한다
    return {k: hud.read_number(img, box, fast=True) for k, box in boxes.items()}


def _is_orange(img: np.ndarray, center: tuple[int, int], r: int) -> bool:
    x, y = center
    hsv = cv2.cvtColor(img[y - r:y + r, x - r:x + r], cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (5, 150, 180), (25, 255, 255)).mean() / 255 > 0.5


def panel_open(img: np.ndarray) -> bool:
    """마을 패널이 열려 있는지: 패널 위 주황색 탭으로 판단 (OCR 없음)."""
    return _is_orange(img, PANEL_TAB, 10)


def has_next(img: np.ndarray) -> bool:
    """오른쪽 화살표가 주황색이면 다음 마을이 있음. 마지막 마을에서는 회색."""
    return _is_orange(img, NEXT_ARROW, 25)


def assert_safe(x: int, y: int):
    for x1, y1, x2, y2 in FORBIDDEN_BOXES:
        if x1 <= x <= x2 and y1 <= y <= y2:
            raise RuntimeError(f"탭 금지 영역 ({x}, {y})")
