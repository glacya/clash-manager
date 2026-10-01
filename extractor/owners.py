"""마을 보유자 표 (data/owners.csv): 한 사람이 여러 마을(계정)을 가질 수 있음.

열: village_tag, village_name, owner, owner_id
- village_tag는 고유값(PK). owner(보유자 이름), owner_id(보유자 식별 번호)는 사용자가 직접 채움 (API로 얻을 수 없음).
- 개인정보이므로 git에 올리지 않음 (.gitignore).

실행: .venv\\Scripts\\python.exe -m extractor.owners [--war <currentwar.json>] [--members <members.json>]
  현재 클랜원(/members)과 클랜전 참가 아군을 합쳐 표를 만들거나 갱신한다.
  이미 있는 행의 owner, owner_id는 그대로 두고, 새 마을만 추가하고, 마을 이름이 바뀌었으면 이름만 갱신한다.
"""
import argparse
import csv

from . import api
from .paths import ROOT

OWNERS_CSV = ROOT / "data" / "owners.csv"
FIELDS = ["village_tag", "village_name", "owner", "owner_id"]


def load() -> dict[str, dict]:
    """village_tag → 행. 파일이 없으면 빈 dict."""
    if not OWNERS_CSV.exists():
        return {}
    return {r["village_tag"]: r for r in csv.DictReader(open(OWNERS_CSV, encoding="utf-8-sig"))}


def update(villages: list[dict]) -> tuple[int, int]:
    """villages: [{"tag", "name"}]. (추가된 수, 이름이 바뀐 수)"""
    rows = load()
    added = renamed = 0
    for v in villages:
        row = rows.get(v["tag"])
        if row is None:
            rows[v["tag"]] = {"village_tag": v["tag"], "village_name": v["name"], "owner": "", "owner_id": ""}
            added += 1
        elif row["village_name"] != v["name"]:
            row["village_name"] = v["name"]
            renamed += 1
    OWNERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OWNERS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows.values())
    return added, renamed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--war", help="currentwar JSON 파일 (생략하면 API에서 받음)")
    parser.add_argument("--members", help="members JSON 파일 (생략하면 API에서 받음)")
    args = parser.parse_args()

    members = api.load_members(args.members)["items"]
    war_allies = api.load_war(args.war).get("clan", {}).get("members", [])
    villages = {}
    # 마을회관 레벨 높은 순으로 보기 좋게 (이미 있는 행의 순서는 유지됨)
    for m in sorted(members, key=lambda m: (-m["townHallLevel"], m["name"])):
        villages[m["tag"]] = {"tag": m["tag"], "name": m["name"]}
    for m in sorted(war_allies, key=lambda m: m["mapPosition"]):  # 전쟁 후 클랜을 떠난 마을도 포함
        villages.setdefault(m["tag"], {"tag": m["tag"], "name": m["name"]})

    added, renamed = update(list(villages.values()))
    total = len(load())
    print(f"저장: {OWNERS_CSV}  (전체 {total}개 마을, 새로 추가 {added}, 이름 갱신 {renamed})")


if __name__ == "__main__":
    main()
