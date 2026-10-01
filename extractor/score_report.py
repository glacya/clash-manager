"""아군 수행도 점수표 (클랜전 리그용으로 설계, 일반 클랜전 데이터로 연구 중).

실행: .venv\\Scripts\\python.exe -m extractor.score_report <war_report 폴더>
        [--war <currentwar.json>] [--members <members.json>]
        [--w 0.5] [--c 1] [--defense-weight 0.75] [--auto-p 0.5]
입력: <war_report 폴더>/ally.csv, enemy.csv (war_report.py 결과, 파워), 공격·방어 기록은 currentwar, 티어는 members
출력: <war_report 폴더>/ally_score.csv (total 내림차순. 요약 열이 power 바로 다음)

점수 단위는 "별"에 맞춤 (3성 공격 1회 ≈ 3점):
  트로피        경쟁전 규칙으로 공격자/방어자가 얻는 트로피 (0~40)
  공격 점수     공격 1회마다 [공격자 트로피 × 3/40 × r^w × a^(1-w)] + 티어 보너스 + 파워 보너스
                  r = 상대 파워 / 내 파워, a = 상대 파워 / P_MAX (상대의 절대적 강도)
                  w = 1이면 순수 비율, 작을수록 상대의 절대적 강도를 더 반영 (강한 아군에게 유리)
                  티어 보너스 = 티어 / 144 (0 ~ 0.25별), 파워 보너스 = 0.25 × max(0, 1 - c × (P_MAX - P) / P_MAX)
                  → 공격하지 않으면 보너스도 받지 못함
  방어 점수     DEFENSE_WEIGHT × Σ 방어자 트로피 × 3/40 × (공격자 파워 / 내 파워)
                  중복 공격도 모두 합산 (이미 3성인 마을에 들어온 공격도 같은 취급)
                  공격받지 않은 아군은 '가상 0별 방어' (assign_auto_defenses, 리그 데이터로 추후 정교화)
  총점          total = 공격 + 방어(자동 포함), total_excl_auto = 자동 방어 제외, total_auto_p = 자동 방어 × p
설계 원칙: 클랜전/리그 승패는 공격 성적이 결정적 → 보너스는 공격 1회당 0.5별 정도로 제한, 방어는 공격보다 낮은 가중치.
"""
import argparse
import csv
from pathlib import Path

from . import api, war

# --- 상수 (초기 테스트 외에는 바꿀 일이 거의 없음) ---
BONUS_STAR_VALUE = 0.25                             # 티어, 파워 보너스 각각의 최대치 (별)
P_MAX = war.power(1_575_000, 10_062)                # TH18 최대 전리품 기준 파워 = 3,084,300
TIER_MAX = 36                                       # 해골 1 ~ 일렉트로 33, 전설 III/II/I = 34/35/36
TIER_DIVISOR = TIER_MAX / BONUS_STAR_VALUE          # 144 → 티어 보너스 0 ~ 0.25별
LEAGUE_TIER_ID_BASE = 105_000_000                   # leagueTier.id - 이 값 = 티어 번호 (0 = Unranked)
MIN_LEAGUE_TH = 7                                   # TH7 미만은 경쟁전 참가 불가 → 티어 0
# 마을회관별 최소 티어. Unranked면 (최소 티어 - 1)을 티어로 사용
FLOOR_TIER = {7: 1, 8: 2, 9: 3, 10: 4, 11: 6, 12: 8, 13: 11, 14: 14, 15: 17, 16: 20, 17: 23, 18: 26}
MAX_TROPHIES = 40
STAR_SCALE = 3 / MAX_TROPHIES                       # 트로피 40 → 3별

# --- 조정 파라미터 기본값 ---
DEFAULT_W = 0.5             # 공격 점수에서 상대적 비율(r)과 상대의 절대적 강도(a)의 배합
DEFAULT_C = 1.0             # 파워 보너스 기울기
DEFAULT_DEFENSE_WEIGHT = 0.75  # 방어 점수 가중치 (클랜 수준이 오르면 높임)
DEFAULT_AUTO_P = 0.5        # 자동 방어 점수 반영 비율 (total_auto_p 열)


# ---------- 트로피 (경쟁전 규칙) ----------

def attacker_trophies(stars: int, pct: int) -> int:
    if stars >= 3:
        return 40
    if stars == 2:
        return min(32, 16 + max(0, pct - 50) // 3)
    if stars == 1:
        return min(15, 5 + pct // 9)
    return min(4, pct // 10)


def defender_trophies(stars: int, pct: int) -> int:
    return MAX_TROPHIES if stars == 0 else MAX_TROPHIES - attacker_trophies(stars, pct)


# 위키 예시로 확인
assert attacker_trophies(2, 73) == 23 and defender_trophies(2, 73) == 17
assert attacker_trophies(2, 50) == 16 and attacker_trophies(2, 98) == 32
assert attacker_trophies(1, 1) == 5 and attacker_trophies(1, 91) == 15
assert attacker_trophies(0, 9) == 0 and attacker_trophies(0, 49) == 4 and defender_trophies(0, 49) == 40
assert defender_trophies(3, 100) == 0


# ---------- 보너스 ----------

def league_tier(member: dict | None, th: int) -> int:
    """경쟁전 티어 번호. TH7 미만은 0, Unranked(또는 클랜을 떠나 정보가 없음)이면 TH별 최소 티어 - 1."""
    if th < MIN_LEAGUE_TH:
        return 0
    tier = (member or {}).get("leagueTier", {}).get("id", LEAGUE_TIER_ID_BASE) - LEAGUE_TIER_ID_BASE
    return tier if tier > 0 else FLOOR_TIER[th] - 1


def tier_bonus(tier: int) -> float:
    return tier / TIER_DIVISOR


def power_bonus(power: int, c: float) -> float:
    return BONUS_STAR_VALUE * max(0.0, 1 - c * (P_MAX - power) / P_MAX)


def attack_factor(my_power: int, target_power: int, w: float) -> float:
    r = target_power / my_power
    a = target_power / P_MAX
    return r ** w * a ** (1 - w)


# ---------- 미방어 아군의 가상 방어 ----------

def assign_auto_defenses(war_json: dict, undefended: list[dict]) -> dict[str, dict]:
    """공격받지 않은 아군 → 가상 공격자(상대 멤버). 가상 공격자가 0별을 낸 것으로 본다.

    1. 상대의 미사용 공격권 목록 (mapPosition 순, 공격권이 여러 개 남은 멤버는 그 수만큼 반복)
       과 미방어 아군 목록(mapPosition 순)을 차례로 짝지음.
    2. 미방어 아군이 더 많으면 (상대가 중복 공격) 목록 맨 마지막 상대로 채움: [1, 2] → [1, 2, 2, 2]
    3. 미사용 공격권이 하나도 없으면, 중복 공격(이미 공격받은 마을을 다시 공격)한 상대 중 파워가 가장 높은 상대.
    """
    if not undefended:
        return {}
    per_member = war_json.get("attacksPerMember", 2)
    opponents = sorted(war_json["opponent"]["members"], key=lambda m: m["mapPosition"])
    unused = [m for m in opponents for _ in range(per_member - len(m.get("attacks", [])))]
    if unused:
        attackers = unused + [unused[-1]] * (len(undefended) - len(unused))
    else:
        attacks = sorted((a for m in opponents for a in m.get("attacks", [])), key=lambda a: a["order"])
        hit, dup_tags = set(), set()
        for a in attacks:
            if a["defenderTag"] in hit:
                dup_tags.add(a["attackerTag"])
            hit.add(a["defenderTag"])
        by_tag = {m["tag"]: m for m in opponents}
        dup = [by_tag[t] for t in dup_tags] or opponents
        # 파워가 같으면 번호가 빠른 상대
        strongest = max(dup, key=lambda m: (m["_power"], -m["mapPosition"]))
        attackers = [strongest] * len(undefended)
    return {ally["tag"]: atk for ally, atk in zip(undefended, attackers)}


# ---------- 점수표 ----------

def _powers(path: Path) -> dict[int, int]:
    return {int(r["number"]): int(r["power"]) for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def build(report_dir: Path, war_json: dict, members_json: dict, w: float, c: float, defense_weight: float,
          auto_p: float = 0.5) -> list[dict]:
    ally_power = _powers(report_dir / "ally.csv")
    enemy_power = _powers(report_dir / "enemy.csv")
    allies = sorted(war_json["clan"]["members"], key=lambda m: m["mapPosition"])
    opponents = war_json["opponent"]["members"]
    for m in allies:
        m["_power"] = ally_power[m["mapPosition"]]
    for m in opponents:
        m["_power"] = enemy_power[m["mapPosition"]]
    by_tag = {m["tag"]: m for m in allies + opponents}
    members_by_tag = {m["tag"]: m for m in members_json["items"]}
    per_member = war_json.get("attacksPerMember", 2)

    received = {m["tag"]: [] for m in allies}
    for opp in opponents:
        for a in opp.get("attacks", []):
            received[a["defenderTag"]].append(a)
    auto = assign_auto_defenses(war_json, [m for m in allies if not received[m["tag"]]])

    rows = []
    for m in allies:
        p = m["_power"]
        tier = league_tier(members_by_tag.get(m["tag"]), m["townhallLevel"])
        tb, pb = tier_bonus(tier), power_bonus(p, c)

        # 공격: 공격 1회마다 (트로피 × 3/40 × factor) + 티어 보너스 + 파워 보너스. 공격하지 않으면 보너스도 없음
        detail = {}
        attack_base = 0.0
        attacks = sorted(m.get("attacks", []), key=lambda a: a["order"])
        for i in range(per_member):
            pre = f"attack_{i + 1}_"
            if i < len(attacks):
                a = attacks[i]
                target = by_tag[a["defenderTag"]]
                t = attacker_trophies(a["stars"], a["destructionPercentage"])
                f = attack_factor(p, target["_power"], w)
                base = t * STAR_SCALE * f
                attack_base += base
                detail.update({pre + "enemy": target["mapPosition"], pre + "stars": a["stars"],
                               pre + "pct": a["destructionPercentage"], pre + "trophies": t,
                               pre + "factor": round(f, 4), pre + "base": round(base, 4),
                               pre + "score": round(base + tb + pb, 4)})
            else:
                detail.update({pre + k: None for k in
                               ("enemy", "stars", "pct", "trophies", "factor", "base", "score")})
        n_attacks = len(attacks)
        tier_bonus_sum, power_bonus_sum = tb * n_attacks, pb * n_attacks
        attack_score = attack_base + tier_bonus_sum + power_bonus_sum

        # 방어: 방어자 트로피 × 3/40 × (공격자 파워 / 내 파워), 중복 공격 포함 합산
        defenses = sorted(received[m["tag"]], key=lambda a: a["order"])
        real = defense_weight * sum(defender_trophies(a["stars"], a["destructionPercentage"]) * STAR_SCALE
                                    * by_tag[a["attackerTag"]]["_power"] / p for a in defenses)
        auto_score, auto_attacker = 0.0, None
        if m["tag"] in auto:
            atk = auto[m["tag"]]
            auto_score = defense_weight * defender_trophies(0, 0) * STAR_SCALE * atk["_power"] / p
            auto_attacker = atk["mapPosition"]

        row = {
            "number": m["mapPosition"], "village_tag": m["tag"], "village_name": m["name"], "th": m["townhallLevel"], "power": p,
            # 요약 (보기 편하도록 power 바로 다음)
            "total": round(attack_score + real + auto_score, 4),                 # 자동 방어 그대로 반영
            "total_excl_auto": round(attack_score + real, 4),                    # 자동 방어 제외
            "total_auto_p": round(attack_score + real + auto_p * auto_score, 4),  # 자동 방어 × p
            "attack_score": round(attack_score, 4),
            "defense_score": round(real + auto_score, 4),
            "defense_score_real": round(real, 4),
            "auto_defense_score": round(auto_score, 4),
            "attack_count": n_attacks,
            "attack_base": round(attack_base, 4),
            "tier_bonus_sum": round(tier_bonus_sum, 4),
            "power_bonus_sum": round(power_bonus_sum, 4),
            "tier": tier,
            "tier_bonus_per_attack": round(tb, 4), "power_bonus_per_attack": round(pb, 4),
            # 상세
            **detail,
            "defense_count": len(defenses),
            "defenses": " ".join(f"{by_tag[a['attackerTag']]['mapPosition']}:{a['stars']}★{a['destructionPercentage']}%"
                                 for a in defenses),
            "auto_defense_attacker": auto_attacker,
        }
        rows.append(row)

    for key in ("total_excl_auto", "total_auto_p"):
        for rank, row in enumerate(sorted(rows, key=lambda r: r[key], reverse=True), start=1):
            row[f"rank_{key.removeprefix('total_')}"] = rank
    rows.sort(key=lambda r: r["total"], reverse=True)
    out = []
    for rank, r in enumerate(rows, start=1):
        head = {"rank": rank, "rank_excl_auto": r.pop("rank_excl_auto"), "rank_auto_p": r.pop("rank_auto_p")}
        out.append({**head, **r})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path, help="war_report 폴더")
    parser.add_argument("--war", help="currentwar JSON 파일 (생략하면 API에서 받음)")
    parser.add_argument("--members", help="members JSON 파일 (생략하면 API에서 받음)")
    parser.add_argument("--w", type=float, default=DEFAULT_W, help="공격 점수의 상대 비율 가중 (1 = 순수 비율)")
    parser.add_argument("--c", type=float, default=DEFAULT_C, help="파워 보너스 기울기")
    parser.add_argument("--defense-weight", type=float, default=DEFAULT_DEFENSE_WEIGHT)
    parser.add_argument("--auto-p", type=float, default=DEFAULT_AUTO_P, help="자동 방어 점수 반영 비율 (total_auto_p)")
    args = parser.parse_args()

    table = build(args.report_dir, api.load_war(args.war), api.load_members(args.members),
                  args.w, args.c, args.defense_weight, args.auto_p)
    path = args.report_dir / "ally_score.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=table[0].keys())
        wr.writeheader()
        wr.writerows(table)
    print(f"저장: {path}  (w={args.w:g}, c={args.c:g}, defense_weight={args.defense_weight:g}, auto_p={args.auto_p:g})")
    print(f"{'순위':>3} {'#':>3} {'이름':<10} TH {'공격':>6} {'(기본':>6} {'티어+':>6} {'파워+)':>6} "
          f"{'방어':>6} {'(자동)':>6} {'총점':>6}")
    for r in table:
        print(f"{r['rank']:>3} {r['number']:>3} {r['village_name']:<10} {r['th']:>2} {r['attack_score']:>6.3f} "
              f"{r['attack_base']:>6.3f} {r['tier_bonus_sum']:>6.3f} {r['power_bonus_sum']:>6.3f} "
              f"{r['defense_score']:>6.3f} {r['auto_defense_score']:>6.3f} {r['total']:>6.3f}")


if __name__ == "__main__":
    main()
