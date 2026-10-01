"""아군/적군 파워 표를 같은 형식으로 한 폴더에 만든다.

실행: .venv\\Scripts\\python.exe -m extractor.war_report <적군 war_bonus csv> <아군 ally_loot csv> [--war <currentwar.json>]
출력: output/war_report/<시각>/enemy.csv, ally.csv (열: number, name, th, gold_loot, dark_loot, power)

- 적군: 전쟁 승리 보너스(collect_war_bonus 결과)를 그대로 전리품으로 사용.
- 아군: 마을회관 저장량(collect_ally_loot 결과)에서 전리품 = floor(저장량 × 87.5 / 2).
- 이름, TH 레벨은 API 응답에서 (mapPosition = 화면 번호).
"""
import argparse
import csv
import math
from datetime import datetime
from pathlib import Path

from . import api, war
from .collect_ally_loot import LOOT_FACTOR
from .paths import ROOT

OUT_DIR = ROOT / "output" / "war_report"
FIELDS = ["number", "village_tag", "village_name", "th", "gold_loot", "dark_loot", "power"]


def _int(v):
    return int(v) if v not in (None, "", "None") else None


def _members(side: dict) -> dict[int, dict]:
    return {m["mapPosition"]: m for m in side["members"]}


def build(war_json: dict, enemy_csv: Path, ally_csv: Path) -> tuple[list[dict], list[dict]]:
    enemy_members = _members(war_json["opponent"])
    ally_members = _members(war_json["clan"])

    enemy = []
    for r in csv.DictReader(open(enemy_csv, encoding="utf-8-sig")):
        n = int(r["number"])
        gold, dark = _int(r["gold"]), _int(r["dark_elixir"])
        m = enemy_members.get(n, {})
        enemy.append({"number": n, "village_tag": m.get("tag"), "village_name": m.get("name"), "th": m.get("townhallLevel"),
                      "gold_loot": gold, "dark_loot": dark, "power": war.power(gold, dark)})

    ally = []
    for r in csv.DictReader(open(ally_csv, encoding="utf-8-sig")):
        n = int(r["number"])
        gold_s, dark_s = _int(r["gold_stored"]), _int(r["dark_stored"])
        gold = math.floor(gold_s * LOOT_FACTOR) if gold_s is not None else None
        dark = math.floor(dark_s * LOOT_FACTOR) if dark_s is not None else None
        m = ally_members.get(n, {})
        ally.append({"number": n, "village_tag": m.get("tag"), "village_name": m.get("name"), "th": m.get("townhallLevel"),
                     "gold_loot": gold, "dark_loot": dark, "power": war.power(gold, dark)})
    return sorted(enemy, key=lambda r: r["number"]), sorted(ally, key=lambda r: r["number"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("enemy_csv", type=Path, help="collect_war_bonus 결과 csv")
    parser.add_argument("ally_csv", type=Path, help="collect_ally_loot 결과 csv")
    parser.add_argument("--war", help="currentwar JSON 파일 (생략하면 API에서 받음)")
    parser.add_argument("--out", type=Path, help="출력 폴더 (생략하면 output/war_report/<시각>)")
    args = parser.parse_args()
    war_json = api.load_war(args.war)
    enemy, ally = build(war_json, args.enemy_csv, args.ally_csv)
    out = args.out or OUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("enemy", enemy), ("ally", ally)):
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
    (out / "README.txt").write_text(
        f"war: {war_json['clan']['name']} vs {war_json['opponent']['name']} ({war_json.get('startTime')})\n"
        f"enemy.csv: 전쟁 승리 보너스 ({args.enemy_csv.name})\n"
        f"ally.csv: 마을회관 저장량 × 87.5 / 2 내림 ({args.ally_csv.name})\n"
        f"power = gold_loot + dark_loot × {war.DARK_ELIXIR_WEIGHT}\n", encoding="utf-8")
    print("저장:", out)
    for name, rows in (("적군", enemy), ("아군", ally)):
        print(f"\n[{name}]")
        for r in rows:
            print(f"{r['number']:>2} TH{r['th']} {r['village_name']:<12} {r['gold_loot']:>9} {r['dark_loot']:>6} {r['power']:>9}")


if __name__ == "__main__":
    main()
