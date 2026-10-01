"""정찰 화면에서 마을회관(Town Hall) 위치 찾기.

템플릿: Clash of Clans Fandom 위키의 TH 렌더 이미지 (assets/town_hall/Town_Hall<레벨>[-<무기 레벨>].png).
TH 레벨은 공식 API(멤버 townHallLevel)로 알 수 있으므로 해당 레벨의 템플릿만 매칭한다.

- 정찰 화면 배율은 고정이며 TH는 모두 4x4칸이라 화면상 폭이 비슷함 (TH18 기준 약 127px).
  4x4 건물은 몇 종류 없으므로 크기를 4x4에 맞추는 것 자체가 강한 필터가 된다.
  위키 이미지마다 원본 크기가 달라서, 투명 여백을 잘라낸 뒤 폭을 게임 크기에 맞춘다.
- TM_CCOEFF_NORMED + 알파 마스크. TM_CCORR_NORMED는 판별력이 없었음.
- 하단 UI와 화면 가장자리의 용암 지형에서 오탐이 나므로 기지 영역(SEARCH_BOX)에서만 찾는다.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import layout
from .paths import ROOT

TEMPLATE_DIR = ROOT / "assets" / "town_hall"
SEARCH_BOX = layout.get("scout.town_hall_search_box")  # 하단 UI(순번, 화살표 등) 위까지
GAME_WIDTHS = layout.get("scout.town_hall_widths")     # 화면상 TH 폭 후보 (px)
WORK_SCALE = 0.5                    # 속도를 위해 절반 해상도에서 매칭


@dataclass
class Match:
    template: str
    score: float
    box: tuple[int, int, int, int]  # 1920x1080 기준 (x1, y1, x2, y2)

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.box
        return (x1 + x2) // 2, (y1 + y2) // 2


LEVELS = range(3, 19)
TH17_FALLBACK_SCORE = 0.5  # TH17-5 점수가 이보다 낮으면 17-1~4도 시도


def templates_for(level: int) -> list[Path]:
    """레벨별 기본 템플릿.

    - TH12~15: 무기 레벨이 제거되어 현재 외관은 N-5 이미지와 가장 비슷함 (로마자 V 장식 유무 정도 차이).
    - TH17: 무기 레벨이 남아 있지만 외관 차이는 미미 → 17-5 기준, 필요 시 fallback_templates.
    """
    if 12 <= level <= 15 or level == 17:
        name = f"Town_Hall{level}-5.png"
    else:
        name = f"Town_Hall{level}.png"
    return [TEMPLATE_DIR / name]


def fallback_templates(level: int) -> list[Path]:
    if level == 17:
        return [TEMPLATE_DIR / f"Town_Hall17-{k}.png" for k in range(1, 5)]
    return []


@lru_cache(maxsize=None)
def _load(path: Path) -> np.ndarray:
    rgba = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    ys, xs = np.where(rgba[:, :, 3] > 128)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _prepare(img: np.ndarray) -> np.ndarray:
    sx1, sy1, sx2, sy2 = SEARCH_BOX
    return cv2.resize(img[sy1:sy2, sx1:sx2], None, fx=WORK_SCALE, fy=WORK_SCALE, interpolation=cv2.INTER_AREA)


def locate(img: np.ndarray, level: int, area: np.ndarray | None = None) -> Match:
    """TH 레벨을 알고 있을 때 정찰 화면에서 가장 잘 맞는 위치를 찾는다."""
    area = _prepare(img) if area is None else area
    best = _match(area, templates_for(level))
    if best.score < TH17_FALLBACK_SCORE and fallback_templates(level):
        alt = _match(area, fallback_templates(level))
        best = alt if alt.score > best.score else best
    return best


def candidates(img: np.ndarray, level: int, k: int = 3, min_dist: int = 80) -> list[Match]:
    """점수 상위 k개 후보 위치 (서로 min_dist px 이상 떨어진 것만, 1920x1080 기준)."""
    area = _prepare(img)
    sx1, sy1, _, _ = SEARCH_BOX
    paths = templates_for(level) + fallback_templates(level)
    peaks = []
    for path in paths:
        rgba = _load(path)
        for width in GAME_WIDTHS:
            s = width * WORK_SCALE / rgba.shape[1]
            tpl = cv2.resize(rgba, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            bgr, mask = tpl[:, :, :3], (tpl[:, :, 3] > 128).astype(np.uint8) * 255
            res = np.nan_to_num(cv2.matchTemplate(area, bgr, cv2.TM_CCOEFF_NORMED, mask=mask),
                                nan=-1, posinf=-1, neginf=-1)
            h, w = bgr.shape[:2]
            for _ in range(k):
                _, score, _, (x, y) = cv2.minMaxLoc(res)
                box = (int(x / WORK_SCALE) + sx1, int(y / WORK_SCALE) + sy1,
                       int((x + w) / WORK_SCALE) + sx1, int((y + h) / WORK_SCALE) + sy1)
                peaks.append(Match(path.stem, float(score), box))
                res[max(0, y - h):y + h, max(0, x - w):x + w] = -1
    picked: list[Match] = []
    for m in sorted(peaks, key=lambda m: -m.score):
        if all(np.hypot(m.center[0] - p.center[0], m.center[1] - p.center[1]) >= min_dist for p in picked):
            picked.append(m)
        if len(picked) == k:
            break
    return picked


def locate_any(img: np.ndarray) -> tuple[int, Match]:
    """TH 레벨을 모를 때: 모든 레벨을 매칭해 가장 높은 점수를 고른다 (느림, 검증용)."""
    area = _prepare(img)
    results = [(level, locate(img, level, area)) for level in LEVELS]
    return max(results, key=lambda r: r[1].score)


def _match(area: np.ndarray, paths: list[Path]) -> Match:
    sx1, sy1, _, _ = SEARCH_BOX
    best = None
    for path in paths:
        rgba = _load(path)
        for width in GAME_WIDTHS:
            s = width * WORK_SCALE / rgba.shape[1]
            tpl = cv2.resize(rgba, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            bgr, mask = tpl[:, :, :3], (tpl[:, :, 3] > 128).astype(np.uint8) * 255
            res = cv2.matchTemplate(area, bgr, cv2.TM_CCOEFF_NORMED, mask=mask)
            res = np.nan_to_num(res, nan=-1, posinf=-1, neginf=-1)
            _, score, _, (x, y) = cv2.minMaxLoc(res)
            if best is None or score > best.score:
                h, w = bgr.shape[:2]
                box = (int(x / WORK_SCALE) + sx1, int(y / WORK_SCALE) + sy1,
                       int((x + w) / WORK_SCALE) + sx1, int((y + h) / WORK_SCALE) + sy1)
                best = Match(path.stem, float(score), box)
    return best
