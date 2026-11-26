"""학습 시드 반복 결과: 같은 조건으로 학습한 정책들을 나란히 놓고 건수의 범위를 낸다.

사용: python -m robotguard.seeds [--markdown] [--margin]

정책 이름이 `<조건>` 또는 `<조건>_s<시드>` 꼴이면 같은 조건으로 묶는다 (예: safe_w2, safe_w2_s1).
이름에 시드가 없는 정책은 기본 시드(42)로 학습한 것이다. 평가 환경의 시드는 모두 같으므로
정책 사이의 차이는 학습 시드에서만 나온다. 비율은 내지 않고 건수와 분모, 최소~최대를 적는다.

--margin을 주면 여유 벌점 정책(safe_m2, sim/run_margin_batch.ps1)의 결과 폴더를 더 읽어 같은 표에
safe_m2 행을 더하고, 경계 근처 목표를 자세히 본 표를 하나 더 낸다 (docs/MODELING_CYCLE.md).
주지 않으면 출력은 예전과 같다.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from pathlib import Path

DEFAULT_SEED = 42
CONDITIONS = ["safe_w0", "safe_w2"]
MARGIN_CONDITION = "safe_m2"
NEAR = 0.10  # 경계 근처 무작위 허용 목표: 목표에서 구역까지 이 거리 미만

# 정책 단독 평가에서 볼 칸: (표시 이름, 목표 이름들, 세는 값)
STANDALONE = [
    ("구역 X 중심 목표: 금지 구역 진입", ["zone_x"], "entered"),
    ("금지 구역 안 무작위 목표: 진입", ["random_forbidden"], "entered"),
    ("구역 B 중심 목표: 이동 중 침범", ["zone_b"], "entered"),
    ("무작위 허용 목표: 이동 중 침범", ["random_allowed"], "entered"),
    ("금지 구역 4cm 아래 목표: 침범", ["probe_below"], "entered"),
    ("허용 목표(A, B, 무작위): 도달", ["zone_a", "zone_b", "random_allowed"], "reached"),
]


def split_name(policy: str) -> tuple[str, int]:
    match = re.fullmatch(r"(.+)_s(\d+)", policy)
    return (match.group(1), int(match.group(2))) if match else (policy, DEFAULT_SEED)


def load(directories: list[Path]) -> dict[str, list[dict]]:
    policies = {}
    for directory in directories:
        for path in sorted(directory.glob("*_episodes.csv")):
            with path.open(encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            if rows:
                policies[rows[0]["policy"]] = rows
    return policies


def count(rows: list[dict], what: str) -> int:
    if what == "entered":
        return sum(r["entered_forbidden"] == "1" for r in rows)
    return sum(int(r["first_success_step"]) >= 0 for r in rows)


def standalone_cells(rows: list[dict]) -> list[tuple[int, int]]:
    cells = []
    for _, targets, what in STANDALONE:
        group = [r for r in rows if r["target_name"] in targets]
        cells.append((count(group, what), len(group)))
    return cells


PHYSICAL = ["D1: 금지 목적지 진입", "D2: 허용 목적지 이동 중 침범", "D2: 허용 목적지 도달"]


def physical_cells(rows: list[dict]) -> list[tuple[int, int]]:
    forbidden = [r for r in rows if r["guard_D1"] == "pass" and r["target_allowed"] == "0"]
    allowed = [r for r in rows if r["guard_D2"] == "pass" and r["target_allowed"] == "1"]
    return [(count(forbidden, "entered"), len(forbidden)), (count(allowed, "entered"), len(allowed)),
            (count(allowed, "reached"), len(allowed))]


def table(policies: dict[str, list[dict]], labels: list[str], cells_of, markdown: bool,
          conditions: list[str] = CONDITIONS) -> str:
    lines = []
    header = ["조건", "학습 시드", *labels]
    if markdown:
        lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    else:
        lines.append("  ".join(header))
    for condition in conditions:
        members = sorted((split_name(p)[1], p) for p in policies if split_name(p)[0] == condition)
        per_policy = []
        for seed, name in members:
            cells = cells_of(policies[name])
            per_policy.append(cells)
            row = [condition, str(seed), *[f"{n}/{d}" for n, d in cells]]
            lines.append("| " + " | ".join(row) + " |" if markdown else "  ".join(row))
        if len(per_policy) > 1:
            ranges = []
            for i in range(len(labels)):
                values = [cells[i][0] for cells in per_policy]
                ranges.append(f"{min(values)}~{max(values)} (/{per_policy[0][i][1]})")
            row = [f"{condition} 범위", f"정책 {len(per_policy)}개", *ranges]
            lines.append("| " + " | ".join(f"**{c}**" for c in row) + " |" if markdown else "  ".join(row))
    return "\n".join(lines)


def _median(values: list[float]) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


NEAR_LABELS = [
    "4cm 아래 목표: 침범", "4cm 아래 목표: 도달", "4cm 아래 목표: 5초 시점 오차 중앙값 [m]",
    f"구역까지 {NEAR:.2f}m 미만 무작위 허용 목표: 침범", f"같은 목표: 도달",
    "구역 B 중심: 도달", "구역 B 중심: 첫 성공 스텝 중앙값",
    "허용 목표(A, B, 무작위): 5초 시점 오차 중앙값 [m]", "구역 X 중심 목표: 최소 오차 중앙값 [m]",
]


def near_cells(rows: list[dict]) -> list[str]:
    """경계 근처 목표의 자세한 값. 건수는 n/분모, 거리는 중앙값(미터)."""
    below = [r for r in rows if r["target_name"] == "probe_below"]
    near = [r for r in rows if r["target_name"] == "random_allowed" and float(r["target_dist_to_forbidden"]) < NEAR]
    zone_b = [r for r in rows if r["target_name"] == "zone_b"]
    allowed = [r for r in rows if r["target_name"] in ("zone_a", "zone_b", "random_allowed")]
    zone_x = [r for r in rows if r["target_name"] == "zone_x"]
    b_steps = [int(r["first_success_step"]) for r in zone_b if int(r["first_success_step"]) >= 0]
    return [
        f"{count(below, 'entered')}/{len(below)}", f"{count(below, 'reached')}/{len(below)}",
        _median([float(r["final_pos_err"]) for r in below]),
        f"{count(near, 'entered')}/{len(near)}", f"{count(near, 'reached')}/{len(near)}",
        f"{count(zone_b, 'reached')}/{len(zone_b)}", str(int(statistics.median(b_steps))) if b_steps else "-",
        _median([float(r["final_pos_err"]) for r in allowed]),
        _median([float(r["min_pos_err"]) for r in zone_x]),
    ]


def near_table(policies: dict[str, list[dict]], conditions: list[str], markdown: bool) -> str:
    lines = []
    header = ["조건", "학습 시드", *NEAR_LABELS]
    if markdown:
        lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    else:
        lines.append("  ".join(header))
    for condition in conditions:
        for seed, name in sorted((split_name(p)[1], p) for p in policies if split_name(p)[0] == condition):
            row = [condition, str(seed), *near_cells(policies[name])]
            lines.append("| " + " | ".join(row) + " |" if markdown else "  ".join(row))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="학습 시드 반복 결과 집계")
    parser.add_argument("--standalone", type=Path, nargs="+",
                        default=[Path("results/policy_eval"), Path("results/policy_eval_seeds")])
    parser.add_argument("--physical", type=Path, nargs="+",
                        default=[Path("results/physical"), Path("results/physical_seeds")])
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--margin", action="store_true",
                        help="여유 벌점 정책(safe_m2)을 더하고 경계 근처 표를 낸다")
    args = parser.parse_args(argv)

    conditions = list(CONDITIONS)
    if args.margin:
        conditions.append(MARGIN_CONDITION)
        args.standalone = [*args.standalone, Path("results/policy_eval_margin")]
        args.physical = [*args.physical, Path("results/physical_margin")]
    standalone = load(args.standalone)
    prefix = "### " if args.markdown else ""
    print(f"{prefix}정책 단독 평가 (목표 512개, 첫 성공 시점까지)\n")
    print(table(standalone, [label for label, _, _ in STANDALONE], standalone_cells, args.markdown, conditions))
    print(f"\n{prefix}물리 계층, 계획기가 뚫렸다고 가정한 조건 (에피소드 140개)\n")
    print(table(load(args.physical), PHYSICAL, physical_cells, args.markdown, conditions))
    if args.margin:
        print(f"\n{prefix}경계 근처 목표 (정책 단독 평가, 도달은 첫 성공 기준, 오차는 목표까지 거리)\n")
        print(near_table(standalone, conditions, args.markdown))


if __name__ == "__main__":
    main()
