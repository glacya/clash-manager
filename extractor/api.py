"""Clash of Clans 공식 API 클라이언트.

.env: CLASH_API_KEY (발급 시 등록한 IP에서만 동작), CLAN_TAG (예: #29CG8YYP2).
실행: .venv\\Scripts\\python.exe -m extractor.api   # 현재 클랜전 정보를 output/api/에 저장
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .paths import ROOT

BASE_URL = "https://api.clashofclans.com/v1"
OUT_DIR = ROOT / "output" / "api"


def _load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get(path: str) -> dict:
    _load_env()
    key = os.environ.get("CLASH_API_KEY")
    if not key:
        raise RuntimeError(".env에 CLASH_API_KEY가 없습니다")
    req = urllib.request.Request(BASE_URL + path, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # 403 accessDenied.invalidIp: 키에 등록한 IP와 현재 IP가 다름
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from None


def clan_tag() -> str:
    _load_env()
    tag = os.environ.get("CLAN_TAG")
    if not tag:
        raise RuntimeError(".env에 CLAN_TAG가 없습니다")
    return tag


def current_war(tag: str | None = None) -> dict:
    """현재 클랜전. 태그의 #은 %23으로 인코딩해야 함."""
    return get(f"/clans/{urllib.parse.quote(tag or clan_tag(), safe='')}/currentwar")


def league_group(tag: str | None = None) -> dict:
    """현재 클랜전 리그 그룹: 참가 클랜 8개와 라운드별 전쟁 태그 (rounds[i].warTags)."""
    return get(f"/clans/{urllib.parse.quote(tag or clan_tag(), safe='')}/currentwar/leaguegroup")


def league_war(war_tag: str) -> dict:
    """리그전 전쟁 하나 (rounds의 warTag). 아직 정해지지 않은 전쟁 태그는 '#0'."""
    return get(f"/clanwarleagues/wars/{urllib.parse.quote(war_tag, safe='')}")


def clan_members(tag: str | None = None) -> dict:
    """클랜원 목록. 각 멤버의 leagueTier(경쟁전 티어), townHallLevel 등."""
    return get(f"/clans/{urllib.parse.quote(tag or clan_tag(), safe='')}/members")


def _save(name: str, data: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_current_war() -> tuple[dict, Path]:
    war = current_war()
    return war, _save("currentwar", war)


def load_members(path: str | Path | None = None) -> dict:
    """path가 있으면 그 JSON 파일, 없으면 API에서 클랜원 목록을 받아 output/api/에 저장하고 반환.
    경쟁전 티어는 시점마다 바뀌므로 스냅샷을 남긴다."""
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    members = clan_members()
    print(f"API members: {len(members.get('items', []))}명 → {_save('members', members)}")
    return members


def load_war(path: str | Path | None = None) -> dict:
    """path가 있으면 그 JSON 파일, 없으면 API에서 현재 클랜전을 받아 output/api/에 저장하고 반환."""
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    war, saved = save_current_war()
    print(f"API currentwar: state={war.get('state')} → {saved}")
    return war


def main():
    _, path = save_current_war()
    print("저장:", path)


if __name__ == "__main__":
    main()
