"""클랜전 리그(CWL) API: 리그 그룹과 라운드별 우리 전쟁.

- leaguegroup의 rounds[i].warTags(4개) 중 우리 클랜이 있는 전쟁이 그 라운드의 우리 전쟁.
- 우리 클랜이 clan일지 opponent일지 정해져 있지 않으므로 normalize()로 항상 clan = 우리로 맞춘다.
- 리그전은 공격권이 1개이고 응답에 attacksPerMember가 없으므로 1로 채운다 (score_report가 사용).
- 응답은 output/cwl/<season>/api/ 에 저장 (leaguegroup.json, round<N>.json).
"""
import json
from pathlib import Path

from . import api
from .paths import ROOT

OUT_ROOT = ROOT / "output" / "cwl"
PLAYED_STATES = ("inWar", "warEnded")  # 파워 수집/점수 계산 대상 (preparation, notInWar 제외)


def season_dir(season: str) -> Path:
    return OUT_ROOT / season


def normalize(war: dict, clan_tag: str) -> dict:
    """우리 클랜을 'clan'으로, attacksPerMember = 1."""
    if war["opponent"]["tag"] == clan_tag:
        war["clan"], war["opponent"] = war["opponent"], war["clan"]
    war.setdefault("attacksPerMember", 1)
    return war


def fetch(save: bool = True) -> tuple[dict, dict[int, dict]]:
    """(leaguegroup, {라운드 번호: 우리 전쟁(normalize됨)}). 아직 정해지지 않은 라운드('#0')는 빠짐."""
    tag = api.clan_tag()
    group = api.league_group()
    wars = {}
    for n, rnd in enumerate(group["rounds"], start=1):
        for war_tag in rnd["warTags"]:
            if war_tag == "#0":
                continue
            war = api.league_war(war_tag)
            if tag in (war["clan"]["tag"], war["opponent"]["tag"]):
                war["warTag"] = war_tag
                wars[n] = normalize(war, tag)
                break
    if save:
        d = season_dir(group["season"]) / "api"
        d.mkdir(parents=True, exist_ok=True)
        (d / "leaguegroup.json").write_text(json.dumps(group, ensure_ascii=False, indent=2), encoding="utf-8")
        for n, war in wars.items():
            (d / f"round{n}.json").write_text(json.dumps(war, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"API 저장: {d}  (라운드 {sorted(wars)})")
    return group, wars


def load(season: str) -> tuple[dict, dict[int, dict]]:
    """fetch()로 저장해 둔 응답 읽기."""
    d = season_dir(season) / "api"
    group = json.loads((d / "leaguegroup.json").read_text(encoding="utf-8"))
    wars = {int(p.stem.removeprefix("round")): json.loads(p.read_text(encoding="utf-8"))
            for p in d.glob("round*.json")}
    return group, wars


def summary(wars: dict[int, dict]) -> str:
    lines = []
    for n, w in sorted(wars.items()):
        c, o = w["clan"], w["opponent"]
        lines.append(f"R{n} {w['state']:<11} {c['stars']:>2}★ {c['destructionPercentage']:5.1f}% vs "
                     f"{o['stars']:>2}★ {o['destructionPercentage']:5.1f}% {o['name']}")
    return "\n".join(lines)
