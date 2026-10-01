"""사람(보유자) 단위 종합 점수. 클랜 방침: 한 사람당 최대 1보너스 → 계정 성적을 사람 단위로 묶어 순위를 매김.
리그전(CWL) 기준으로 설계: 전쟁 7번, 계정당 전쟁마다 공격권 1개.

실행: .venv\\Scripts\\python.exe -m extractor.person_score <war_report 폴더> [<war_report 폴더> ...] [--k 3] [--p 0.75] [--out <csv>]
  여러 전쟁(리그전 7라운드 등)의 ally_score.csv를 합산. 보유자는 data/owners.csv (village_tag → owner, owner_id).
출력: 기본은 마지막 war_report 폴더의 person_score.csv

종합 점수 = 공격권당 평균 + 별 획득률
  공격권당 평균 = Σ total / Σ 사용한 공격권
                 (방어 점수도 분자에 포함: 리그전에서는 같은 마을에 2번 이상 공격이 거의 안 들어오고,
                  들어오면 그만큼 이득이므로 점수를 더 줘도 됨)
  별 획득률     = (Σ 획득한 별 + k × p) / (공격권 수 × 3 + k)   (0 ~ 1, 베이지안 평활)
                 = "별 획득률 p짜리 가상 공격을 k/3번 추가"한 것. p < 1이라 공격권이 적을수록 더 끌어내려짐
                   → 전부 완파했을 때 공격권이 많은 사람이 아주 약간 높음 (많을수록 전부 완파가 어려움을 반영)
                 평균 파괴율이 100%면 계정 수와 무관하게 거의 같은 점수. 공격권이 많은 사람의
                 한두 번 실수는 비율로 희석되어 조금 덜 깎임 (다계정자의 실수를 조금 봐주는 효과)
  미사용 공격권이 하나라도 있으면 0점 (다른 계정으로 전부 3성을 내도 마찬가지. 클랜 방침)
"""
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from . import owners

MAX_STARS = 3
DEFAULT_K = 3.0   # 별 획득률 평활: 가상 별 수 (3 = 가상 공격 1회분)
DEFAULT_P = 0.75  # 별 획득률 평활: 가상 공격의 별 획득률


def _attack_slots(header: list[str]) -> list[int]:
    """ally_score.csv의 attack_N_ 번호들 = 전쟁당 계정별 공격권 (일반 클랜전 2, 리그전 1)."""
    return [int(m.group(1)) for h in header if (m := re.fullmatch(r"attack_(\d+)_enemy", h))]


def build(report_dirs: list[Path], k: float = DEFAULT_K, prior: float = DEFAULT_P) -> list[dict]:
    owner_of = owners.load()
    people = defaultdict(lambda: {"villages": [], "attacks": 0, "available": 0, "total": 0.0,
                                  "attack": 0.0, "defense": 0.0, "auto_defense": 0.0, "stars": 0})
    missing = set()
    for d in report_dirs:
        with open(d / "ally_score.csv", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            slots = _attack_slots(reader.fieldnames)
            rows = list(reader)
        for r in rows:
            o = owner_of.get(r["village_tag"])
            if o is None or not o["owner_id"]:
                missing.add(f"{r['village_tag']} {r['village_name']}")
                continue
            p = people[o["owner_id"]]
            p["owner"] = o["owner"]
            if r["village_name"] not in p["villages"]:
                p["villages"].append(r["village_name"])
            p["attacks"] += int(r["attack_count"])
            p["available"] += len(slots)
            p["stars"] += sum(int(r[f"attack_{i}_stars"]) for i in slots if r[f"attack_{i}_stars"])
            p["total"] += float(r["total"])
            p["attack"] += float(r["attack_score"])
            p["defense"] += float(r["defense_score"])
            p["auto_defense"] += float(r["auto_defense_score"])
    if missing:
        raise SystemExit(f"data/owners.csv에 보유자가 없는 마을: {sorted(missing)}  → python -m extractor.owners 후 채우기")

    out = []
    for owner_id, p in people.items():
        unused = p["available"] - p["attacks"]
        avg = p["total"] / p["attacks"] if p["attacks"] else 0.0
        obtainable = p["available"] * MAX_STARS
        raw = p["stars"] / obtainable if obtainable else 0.0
        share = (p["stars"] + k * prior) / (obtainable + k) if obtainable else 0.0
        out.append({
            "owner_id": owner_id, "owner": p["owner"],
            "final": 0.0 if unused else round(avg + share, 4),
            "avg_per_attack": round(avg, 4),
            "star_rate": round(share, 4), "star_rate_raw": round(raw, 4),
            "attacks_unused": unused,
            "attacks_used": p["attacks"], "attacks_available": p["available"],
            "stars_earned": p["stars"], "stars_obtainable": obtainable,
            "total_sum": round(p["total"], 4), "attack_sum": round(p["attack"], 4),
            "defense_sum": round(p["defense"], 4), "auto_defense_sum": round(p["auto_defense"], 4),
            "village_count": len(p["villages"]), "villages": ", ".join(p["villages"]),
        })
    # 미사용 공격권이 있는 사람(0점)끼리는 참고용으로 원래 점수 순
    out.sort(key=lambda r: (r["final"], r["avg_per_attack"] + r["star_rate"]), reverse=True)
    return [{"rank": i, **r} for i, r in enumerate(out, start=1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dirs", type=Path, nargs="+", help="war_report 폴더들 (각각 ally_score.csv 필요)")
    parser.add_argument("--k", type=float, default=DEFAULT_K, help="별 획득률 평활: 가상 별 수 (3 = 가상 공격 1회)")
    parser.add_argument("--p", type=float, default=DEFAULT_P, help="별 획득률 평활: 가상 공격의 별 획득률")
    parser.add_argument("--out", type=Path, help="출력 csv (생략하면 마지막 폴더의 person_score.csv)")
    args = parser.parse_args()

    table = build(args.report_dirs, args.k, args.p)
    path = args.out or args.report_dirs[-1] / "person_score.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=table[0].keys())
        w.writeheader()
        w.writerows(table)
    print(f"저장: {path}  (전쟁 {len(args.report_dirs)}개, k={args.k:g}, p={args.p:g})")
    print(f"{'순위':>3} {'보유자':<8} {'최종':>6} = {'평균':>6} + {'별획득률':>6} ({'평활전':>5}) | 별  | 공격 사용/가능  계정")
    for r in table:
        note = "  ← 미사용 공격권" if r["attacks_unused"] else ""
        print(f"{r['rank']:>3} {r['owner']:<8} {r['final']:>6.3f} = {r['avg_per_attack']:>6.3f} + {r['star_rate']:>6.3f} "
              f"({r['star_rate_raw']:>5.3f}) | "
              f"{r['stars_earned']:>3}/{r['stars_obtainable']:<3}| {r['attacks_used']:>3}/{r['attacks_available']:<3}  {r['villages']}{note}")


if __name__ == "__main__":
    main()
