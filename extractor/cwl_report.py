"""클랜전 리그 통합 보고서: 라운드별 파워(collect_cwl 결과) + API 성적 → 계정별·사람별 최종 점수.

리그전이 완전히 끝난 뒤(7일차 후) 실행해 성적을 확정하는 것이 목표. 그 전에는 끝난 라운드까지만 계산.
실행: .venv\\Scripts\\python.exe -m extractor.cwl_report [--season 2026-10] [--no-fetch] [--include-inwar]
       [--w 0.5] [--c 1] [--defense-weight 0.75] [--auto-p 0.5] [--k 3] [--p 0.75]
  기본: API에서 리그 그룹과 전쟁을 새로 받아 저장(output/cwl/<season>/api/)한 뒤 계산.
  --no-fetch: 저장해 둔 API 응답으로 계산 (파라미터만 바꿔 다시 계산할 때).
  --include-inwar: 진행 중인 라운드도 포함 (기본은 warEnded만 = 확정된 성적만).
출력: output/cwl/<season>/
  round<N>/ally_power.csv, enemy_power.csv, ally_score.csv   (라운드별, 기존 score_report와 같은 형식)
  ally_score_all.csv   모든 라운드의 계정별 점수를 한 표로 (round 열)
  person_score.csv     사람 단위 종합 점수 (person_score와 같은 규칙: 미사용 공격권이 있으면 0점)

출전하지 않은 라운드는 그 라운드 전쟁의 members에 없으므로 공격권도 없음 (미사용으로 치지 않음).
"""
import argparse
import csv
import json
from pathlib import Path

from . import api, cwl, person_score, score_report, war_report


def _write(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def build_round(rdir: Path, war: dict, members: dict, args) -> list[dict] | None:
    enemy_csv, ally_csv = rdir / "enemy.csv", rdir / "ally.csv"
    if not (enemy_csv.exists() and ally_csv.exists()):
        print(f"{rdir.name}: 파워 수집 결과 없음 (collect_cwl 먼저) → 건너뜀")
        return None
    enemy, ally = war_report.build(war, enemy_csv, ally_csv)
    # score_report.build는 report_dir의 ally.csv/enemy.csv(파워 표)를 읽음 → 라운드 폴더 안 별도 폴더에 둠
    pdir = rdir / "report"
    pdir.mkdir(exist_ok=True)
    for name, rows in (("enemy", enemy), ("ally", ally)):
        with open(pdir / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=war_report.FIELDS)
            w.writeheader()
            w.writerows(rows)
    table = score_report.build(pdir, json.loads(json.dumps(war)), members, args.w, args.c,
                               args.defense_weight, args.auto_p)
    _write(pdir / "ally_score.csv", table)
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", help="예: 2026-10-01 (생략하면 API의 현재 시즌)")
    parser.add_argument("--no-fetch", action="store_true", help="저장된 API 응답 사용")
    parser.add_argument("--include-inwar", action="store_true", help="진행 중인 라운드도 포함")
    parser.add_argument("--members", help="members JSON (생략하면 API에서 받음, 티어 보너스용)")
    parser.add_argument("--w", type=float, default=score_report.DEFAULT_W)
    parser.add_argument("--c", type=float, default=score_report.DEFAULT_C)
    parser.add_argument("--defense-weight", type=float, default=score_report.DEFAULT_DEFENSE_WEIGHT)
    parser.add_argument("--auto-p", type=float, default=score_report.DEFAULT_AUTO_P)
    parser.add_argument("--k", type=float, default=person_score.DEFAULT_K)
    parser.add_argument("--p", type=float, default=person_score.DEFAULT_P)
    args = parser.parse_args()

    if args.no_fetch:
        group, wars = cwl.load(args.season)
    else:
        group, wars = cwl.fetch()
    print(cwl.summary(wars))
    base = cwl.season_dir(group["season"])
    states = ("warEnded", "inWar") if args.include_inwar else ("warEnded",)
    members = api.load_members(args.members)

    all_rows, report_dirs = [], []
    for n, war in sorted(wars.items()):
        if war["state"] not in states:
            continue
        table = build_round(base / f"round{n}", war, members, args)
        if table is None:
            continue
        report_dirs.append(base / f"round{n}" / "report")
        all_rows += [{"round": n, **r} for r in table]
    if not all_rows:
        raise SystemExit("계산할 라운드가 없습니다.")

    # 라운드마다 열 구성이 같으므로 그대로 합침
    _write(base / "ally_score_all.csv", all_rows)
    people = person_score.build(report_dirs, args.k, args.p)
    _write(base / "person_score.csv", people)
    print(f"\n라운드 {[int(d.parent.name.removeprefix('round')) for d in report_dirs]} 반영 → {base}")
    print(f"{'순위':>3} {'보유자':<8} {'최종':>6} = {'평균':>6} + {'별획득률':>6} | 별     | 공격")
    for r in people:
        note = "  ← 미사용 공격권" if r["attacks_unused"] else ""
        print(f"{r['rank']:>3} {r['owner']:<8} {r['final']:>6.3f} = {r['avg_per_attack']:>6.3f} + {r['star_rate']:>6.3f} | "
              f"{r['stars_earned']:>3}/{r['stars_obtainable']:<3}| {r['attacks_used']:>2}/{r['attacks_available']:<2} "
              f"{r['villages']}{note}")


if __name__ == "__main__":
    main()
