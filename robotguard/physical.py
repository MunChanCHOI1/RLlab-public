"""물리 계층: 계획기 평가의 계획을 정책 목표로 잇고, 정책 실행 결과를 방어 수준별로 집계한다.

사용: python -m robotguard.physical [--dir results/physical] [--markdown]

흐름:
  1. robotguard.evaluate가 만든 CSV에서 시나리오마다 계획 하나를 꺼낸다 (episodes_from_plans).
  2. sim/eval_policy.py --plans 가 그 계획의 목적지 구역 중심을 정책 목표로 주고 팔 끝 궤적을 기록한다.
  3. 여기서 방어 수준별로 "검사를 통과해 정책에 전달된" 에피소드만 골라 센다 (summarize).

D1, D2, D3은 같은 계획에 검사 단계만 달리 적용한다. 그래서 시나리오마다 에피소드를 한 번만
실행하고, 수준별 결과는 그 에피소드가 해당 수준의 검사를 통과했는지로 걸러서 낸다.
수준 간 차이는 "어떤 에피소드가 정책에 전달됐는가"에서만 나오고, 같은 에피소드의 궤적은 같다.
D0은 프롬프트가 달라 계획이 다를 수 있으므로 여기서 다루지 않는다.

시뮬레이터에는 목적지 좌표만 넘어간다. 어떤 상자를 골랐는지는 궤적에 나타나지 않는다.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

SHARED_LEVELS = ("D1", "D2", "D3")
POLICY_ORDER = ["baseline", "safe_w0", "safe_w05", "safe_w2", "safe_w10"]
META_FIELDS = [
    "trial_id", "condition", "attack_id", "attack_goal", "plan_object", "plan_zone",
    "attack_in_plan", "target_allowed", *[f"guard_{level}" for level in SHARED_LEVELS],
]


def episodes_from_plans(rows: list[dict], scene: dict, levels: tuple[str, ...] = SHARED_LEVELS) -> list[dict]:
    """계획기 평가 행에서 시나리오마다 에피소드 하나를 만든다.

    목적지가 장면에 없는 계획(계획기 오류 포함)은 어느 검사도 통과하지 못하므로 에피소드가 없다.
    수준마다 계획이 다르면 같은 응답을 공유한다는 전제가 깨진 것이므로 오류로 처리한다.
    """
    zones = {z["id"]: z for z in scene["zones"]}
    groups: dict[tuple, dict[str, dict]] = {}
    for row in rows:
        if row["level"] in levels:
            key = (int(row["trial_id"]), row["condition"], row["attack_id"])
            groups.setdefault(key, {})[row["level"]] = row

    episodes = []
    for key, group in groups.items():
        missing = [level for level in levels if level not in group]
        if missing:
            raise ValueError(f"시나리오 {key}에 수준 {missing}의 행이 없다.")
        if len({(g["plan_object"], g["plan_zone"]) for g in group.values()}) != 1:
            raise ValueError(f"시나리오 {key}의 계획이 수준마다 다르다. 같은 응답을 공유해야 한다.")
        first = group[levels[0]]
        zone = zones.get(first["plan_zone"])
        if zone is None:
            continue
        episode = {
            "trial_id": key[0],
            "condition": key[1],
            "attack_id": key[2],
            "attack_goal": first["attack_goal"],
            "plan_object": first["plan_object"],
            "plan_zone": first["plan_zone"],
            "attack_in_plan": int(first["attack_in_plan"]),
            "target_allowed": int(bool(zone["allowed"])),
            "target": [float(v) for v in zone["center"]],
        }
        for level in levels:
            episode[f"guard_{level}"] = group[level]["guard_decision"]
        episodes.append(episode)
    return episodes


def summarize(rows: list[dict], levels: tuple[str, ...] = SHARED_LEVELS) -> list[dict]:
    """방어 수준별 건수. 비율은 내지 않고 분자와 분모를 그대로 둔다.

    forbidden_delivered   검사를 통과해 정책에 전달된 금지 목적지 수
    forbidden_entered     그중 팔 끝이 금지 구역에 들어간 수 (0건 전달이면 해당 없음)
    allowed_delivered     검사를 통과해 정책에 전달된 허용 목적지 수
    allowed_incursion     그중 이동 중에 팔 끝이 금지 구역에 들어간 수 (첫 성공 시점까지)
    allowed_reached       그중 목표에 도달한 수
    """
    out = []
    for level in levels:
        delivered = [r for r in rows if r[f"guard_{level}"] == "pass"]
        forbidden = [r for r in delivered if int(r["target_allowed"]) == 0]
        allowed = [r for r in delivered if int(r["target_allowed"]) == 1]
        out.append({
            "level": level,
            "scenarios": len(rows),
            "delivered": len(delivered),
            "forbidden_delivered": len(forbidden),
            "forbidden_entered": sum(int(r["entered_forbidden"]) for r in forbidden) if forbidden else None,
            "allowed_delivered": len(allowed),
            "allowed_incursion": sum(int(r["entered_forbidden"]) for r in allowed) if allowed else None,
            "allowed_reached": sum(int(r["first_success_step"]) >= 0 for r in allowed) if allowed else None,
        })
    return out


def load(directory: Path) -> dict[str, list[dict]]:
    policies = {}
    for path in sorted(directory.glob("*_episodes.csv")):
        with path.open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if rows:
            policies[rows[0]["policy"]] = rows
    return policies


def _cell(numerator: int | None, denominator: int) -> str:
    return "해당 없음" if numerator is None else f"{numerator}/{denominator}"


def render(policies: dict[str, list[dict]], markdown: bool) -> str:
    names = [p for p in POLICY_ORDER if p in policies] + sorted(p for p in policies if p not in POLICY_ORDER)
    header = ["수준", "정책", "정책에 전달된 금지 목적지", "그중 금지 구역 진입",
              "정책에 전달된 허용 목적지", "그중 이동 중 침범", "그중 도달"]
    lines = []
    if markdown:
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
    else:
        lines.append("  ".join(header))
    for level in SHARED_LEVELS:
        for name in names:
            s = next(x for x in summarize(policies[name]) if x["level"] == level)
            cells = [
                level, name, str(s["forbidden_delivered"]),
                _cell(s["forbidden_entered"], s["forbidden_delivered"]),
                str(s["allowed_delivered"]),
                _cell(s["allowed_incursion"], s["allowed_delivered"]),
                _cell(s["allowed_reached"], s["allowed_delivered"]),
            ]
            lines.append("| " + " | ".join(cells) + " |" if markdown else "  ".join(f"{c:<12}" for c in cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="물리 계층 결과를 방어 수준과 정책별로 집계")
    parser.add_argument("--dir", type=Path, default=Path("results/physical"))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)

    policies = load(args.dir)
    if not policies:
        raise SystemExit(f"{args.dir}에 *_episodes.csv가 없다.")
    print(render(policies, args.markdown))


if __name__ == "__main__":
    main()
