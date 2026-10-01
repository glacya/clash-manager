"""화면 좌표·관심 영역(ROI) 설정: config/layout.json

- 코드에 흩어져 있던 좌표를 한 파일로 모음. 파일이 없으면 아래 DEFAULTS로 만들고, 있으면 파일 값이 우선.
- 실행 중 찾아낸 영역(예: 전쟁 보너스 숫자 위치)도 learn()으로 같은 파일에 저장해 다음 실행에서 재사용.
- **PC별 로컬 캐시라 git에서 제외** (PC마다 에뮬레이터 창 크기 = 해상도가 다를 수 있음).
  기본값은 이 파일의 DEFAULTS(1920x1080에서 측정)이며 git으로 추적됨. 새 PC에서는 첫 실행 때 DEFAULTS로 만들어짐.
- 좌표는 모두 reference_size 기준. 점은 [x, y], 영역은 [x1, y1, x2, y2].
  스크린샷 크기가 reference_size와 다르면 check_size()가 경고 (좌표를 그 PC에 맞게 고쳐야 함).
"""
import json
from copy import deepcopy

from .paths import ROOT

LAYOUT_PATH = ROOT / "config" / "layout.json"

DEFAULTS = {
    "reference_size": [1920, 1080],
    "device": {
        "udid": "localhost:6520",  # Google Play Games 개발자 에뮬레이터
    },
    "village": {  # 마을 화면 상단 우측 재화
        "resource_boxes": {
            "gold": [1590, 28, 1835, 74],
            "elixir": [1590, 112, 1835, 158],
            "dark_elixir": [1670, 196, 1835, 242],
            "gems": [1705, 278, 1835, 322],
        },
        "clan_war_button": [65, 728],
    },
    "war": {  # 클랜전 맵에서 마을을 선택했을 때 하단 패널
        "bonus_column": [840, 865, 1010, 975],  # 보너스 숫자 열 전체 (이 안에서 숫자 위치를 찾음)
        "prev_arrow": [565, 895],
        "next_arrow": [1355, 895],
        "panel_tab": [870, 705],                # 패널 위 주황색 탭(^)의 왼쪽 부분
        "home_button": [1800, 540],             # 상대 맵 ↔ 아군 맵
        "scout_button": [810, 990],             # 아군 패널의 정찰
        "forbidden_boxes": [                    # ⚠️ 절대 탭 금지 (상대 패널)
            [1080, 820, 1275, 910],             # 공격!
            [1080, 940, 1275, 1005],            # 정찰
        ],
    },
    "scout": {  # 정찰 화면
        "prev_arrow": [718, 975],
        "next_arrow": [1190, 975],               # 끝에서 반대편으로 순환
        "war_map_button": [105, 975],
        "counter_box": [870, 890, 1040, 940],    # "N/M" 순번
        "pinch_area": [300, 100, 1320, 780],     # 축소 핀치 영역 (left, top, width, height)
        "town_hall_search_box": [280, 20, 1640, 890],
        "town_hall_widths": [117, 127, 137],     # 화면상 TH 폭 후보 (4x4 건물)
        "selected_building_icon": [960, 770],    # 건물 선택 시 "정보" 버튼의 파란 i 아이콘
        "selected_hero_icon": [880, 770],        # 영웅 선택 시 (옆에 "스킨 보기")
        "info_button": [960, 790],
    },
    "info": {  # 건물 정보 창
        "close_button": [1695, 83],
        "weapon_arrow": [1682, 800],             # TH 무기 정보 ↔ 마을회관 정보 전환 (파란 화살표)
        "title_strip": [400, 40, 1520, 110],
        "storage_panel": [920, 180, 1720, 640],
    },
    "learned": {},  # 실행 중 찾아낸 영역 (learn()으로 저장)
}

_cache: dict | None = None


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _save(data: dict):
    LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load() -> dict:
    """기본값 위에 config/layout.json을 덮어쓴 설정. 파일이 없으면 기본값으로 만든다."""
    global _cache
    if _cache is None:
        if LAYOUT_PATH.exists():
            _cache = _merge(DEFAULTS, json.loads(LAYOUT_PATH.read_text(encoding="utf-8")))
        else:
            _cache = deepcopy(DEFAULTS)
            _save(_cache)
    return _cache


def get(path: str):
    """점으로 구분한 경로 (예: "war.next_arrow"). 리스트는 튜플로 반환."""
    node = load()
    for key in path.split("."):
        node = node[key]
    return _tuple(node)


def _tuple(v):
    if isinstance(v, list):
        return tuple(_tuple(x) for x in v)
    if isinstance(v, dict):
        return {k: _tuple(x) for k, x in v.items()}
    return v


_size_warned = False


def check_size(img) -> bool:
    """스크린샷 크기가 reference_size와 같은지. 다르면 한 번만 경고."""
    global _size_warned
    w, h = get("reference_size")
    ok = img.shape[1] == w and img.shape[0] == h
    if not ok and not _size_warned:
        _size_warned = True
        print(f"⚠️ 화면 크기 {img.shape[1]}x{img.shape[0]} ≠ 설정 {w}x{h}. "
              f"에뮬레이터 창 크기를 {w}x{h}로 맞추거나 {LAYOUT_PATH}의 좌표를 이 PC에 맞게 고치세요.")
    return ok


def learned(key: str):
    """learn()으로 저장된 값. 없으면 None."""
    v = load()["learned"].get(key)
    return _tuple(v) if v is not None else None


def learn(key: str, value):
    """실행 중 찾아낸 영역을 config/layout.json의 learned에 저장."""
    data = load()
    data["learned"][key] = json.loads(json.dumps(value))  # 튜플 → 리스트
    _save(data)
