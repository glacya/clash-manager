"""아군의 공격 기록 표: 아군 파워 표에 공격 1/2의 상대, 별, 파괴율, 파워 차이를 붙인다.

실행: .venv\\Scripts\\python.exe -m extractor.attack_report <war_report 폴더> [--war <currentwar.json>]
입력: <war_report 폴더>/ally.csv, enemy.csv (war_report.py 결과), 공격 기록은 공식 API(currentwar)
출력: <war_report 폴더>/ally_attacks.csv

- 공격 순서: API의 order(전쟁 전체의 공격 순서) 오름차순 → 먼저 한 공격이 attack_1.
- attack_N_enemy: 공격한 적군 마을 번호 (defenderTag → 상대 mapPosition)
- attack_N_power_diff_absolute = 적군 파워 - 내 파워 (양수 = 나보다 강한 상대를 공격)
- attack_N_power_diff_relative = 적군 파워 / 내 파워 (1보다 크면 나보다 강한 상대)
- 공격하지 않았으면 해당 칸은 비움.
- 전쟁 중(state=inWar)에 실행하면 이후 공격이 빠지므로 warEnded 상태에서 실행할 것.
"""
import argparse
import csv
from pathlib import Path

from . import api

BASE_FIELDS = ["number", "village_tag", "village_name", "th", "gold_loot", "dark_loot", "power"]
ATTACK_FIELDS = ["enemy", "stars", "percentage", "power_diff_absolute", "power_diff_relative"]
ATTACKS_PER_MEMBER = 2


def _read(path: Path) -> dict[int, dict]:
    return {int(r["number"]): r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def build(war_json: dict, report_dir: Path) -> list[dict]:
    ally = _read(report_dir / "ally.csv")
    enemy = _read(report_dir / "enemy.csv")
    enemy_number = {m["tag"]: m["mapPosition"] for m in war_json["opponent"]["members"]}

    rows = []
    for m in sorted(war_json["clan"]["members"], key=lambda m: m["mapPosition"]):
        base = ally[m["mapPosition"]]
        row = {k: base[k] for k in BASE_FIELDS}
        my_power = int(base["power"]) if base["power"] else None
        attacks = sorted(m.get("attacks", []), key=lambda a: a["order"])
        for i in range(ATTACKS_PER_MEMBER):
            prefix = f"attack_{i + 1}_"
            if i >= len(attacks):
                row.update({prefix + f: None for f in ATTACK_FIELDS})
                continue
            a = attacks[i]
            target = enemy_number[a["defenderTag"]]
            target_power = int(enemy[target]["power"]) if enemy[target]["power"] else None
            diff = target_power - my_power if None not in (target_power, my_power) else None
            row.update({
                prefix + "enemy": target,
                prefix + "stars": a["stars"],
                prefix + "percentage": int(a["destructionPercentage"]),
                prefix + "power_diff_absolute": diff,
                prefix + "power_diff_relative": round(target_power / my_power, 4) if diff is not None else None,
            })
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path, help="war_report 폴더")
    parser.add_argument("--war", help="currentwar JSON 파일 (생략하면 API에서 받음)")
    args = parser.parse_args()
    war_json = api.load_war(args.war)
    report_dir = args.report_dir
    rows = build(war_json, report_dir)
    out = report_dir / "ally_attacks.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print("저장:", out)
    for r in rows:
        parts = []
        for i in (1, 2):
            p = f"attack_{i}_"
            if r[p + "enemy"] is None:
                parts.append("-")
            else:
                parts.append(f"→{r[p + 'enemy']:>2} ★{r[p + 'stars']} {r[p + 'percentage']:>3}% "
                             f"{r[p + 'power_diff_absolute']:+,} (×{r[p + 'power_diff_relative']:.3f})")
        print(f"{r['number']:>2} TH{r['th']} {r['village_name']:<10} {int(r['power']):>9,} | {' | '.join(parts)}")


if __name__ == "__main__":
    main()
