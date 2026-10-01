"""마을 화면 상단 우측의 재화(골드/엘릭서/다크 엘릭서/보석) 판독.

좌표는 1920x1080 기준. 숫자는 흰 글자에 테두리가 있는 폰트라서
흰색 픽셀만 뽑아 검은 글자/흰 배경으로 바꾼 뒤 OCR하면 정확도가 높다.
"""
import re
from dataclasses import dataclass

import cv2
import numpy as np
from rapidocr import RapidOCR

from . import layout

REFERENCE_SIZE = layout.get("reference_size")

# (x1, y1, x2, y2), config/layout.json의 village.resource_boxes
RESOURCE_BOXES = layout.get("village.resource_boxes")

# fast(인식 전용) 모드는 정답이어도 0.88~0.9 정도가 나오는 경우가 있음
MIN_SCORE = 0.8

_ocr = None


def _engine() -> RapidOCR:
    global _ocr
    if _ocr is None:
        _ocr = RapidOCR()
    return _ocr


@dataclass
class Reading:
    value: int | None
    text: str
    score: float


def _white_text_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_not(cv2.inRange(hsv, (0, 0, 200), (180, 60, 255)))
    mask = cv2.resize(mask, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    # 여백이 좁으면 숫자 덩어리 하나를 통째로 놓치는 경우가 있어 넉넉히 둔다
    mask = cv2.copyMakeBorder(mask, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def ordered_text(result) -> str:
    """OCR 조각을 왼쪽부터 정렬해 이어 붙인다 (결과 순서가 섞여 나오는 경우가 있음)."""
    if getattr(result, "boxes", None) is None:  # 인식 전용 모드는 조각 없이 한 줄
        return " ".join(t.strip() for t in result.txts)
    parts = sorted(zip(result.boxes, result.txts), key=lambda p: min(pt[0] for pt in p[0]))
    return " ".join(t.strip() for _, t in parts)


def recognize(prepared: np.ndarray, fast: bool = False):
    """fast=True: 글자 위치 탐지(det)를 건너뛰고 인식만 해서 약 100배 빠름.
    단, 마을 화면 골드처럼 0이 길게 이어지는 숫자는 자릿수를 빠뜨림 (29 000 000 → 290000)."""
    # RapidOCR는 호출 시 넘긴 use_* 설정이 다음 호출까지 남으므로 매번 모두 명시한다
    return _engine()(prepared, use_det=not fast, use_cls=False, use_rec=True)


def detect(prepared: np.ndarray):
    """글자 위치만 찾는다 (인식 없음). 결과의 boxes는 prepared 이미지 좌표."""
    return _engine()(prepared, use_det=True, use_cls=False, use_rec=False)


def read_number(img: np.ndarray, box: tuple[int, int, int, int], fast: bool = False) -> Reading:
    x1, y1, x2, y2 = box
    result = recognize(_white_text_mask(img[y1:y2, x1:x2]), fast)
    if not result.txts:
        return Reading(None, "", 0.0)
    text = ordered_text(result)
    score = float(min(result.scores))
    digits = re.sub(r"[^0-9]", "", text)
    # 숫자와 공백 외의 문자가 섞였으면 오판독으로 간주
    if not digits or re.search(r"[^0-9\s]", text):
        return Reading(None, text, score)
    return Reading(int(digits), text, score)


def read_resources(img: np.ndarray) -> dict[str, Reading]:
    h, w = img.shape[:2]
    if (w, h) != REFERENCE_SIZE:
        img = cv2.resize(img, REFERENCE_SIZE)
    return {name: read_number(img, box) for name, box in RESOURCE_BOXES.items()}


def is_confident(readings: dict[str, Reading]) -> bool:
    return all(r.value is not None and r.score >= MIN_SCORE for r in readings.values())
