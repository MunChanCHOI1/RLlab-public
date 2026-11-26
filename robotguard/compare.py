"""정책 단독 평가 결과(results/policy_eval/*_episodes.csv)를 정책별로 나란히 비교한다.

사용: python -m robotguard.compare [--dir results/policy_eval] [--markdown]

sim/eval_policy.py가 만든 에피소드 CSV만 읽는다. 시뮬레이터가 필요 없다.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

# 표에 나오는 순서와 표시 이름
TARGETS = [
    ("zone_a", "구역 A 중심 (허용)"),
    ("zone_b", "구역 B 중심 (허용)"),
    ("random_allowed", "무작위 허용 점"),
    ("probe_above", "금지 구역 10cm 위 (허용)"),
    ("probe_below", "금지 구역 4cm 아래 (허용)"),
    ("zone_x", "구역 X 중심 (금지)"),
    ("random_forbidden", "금지 구역 안 무작위 점"),
]
POLICY_ORDER = ["baseline", "safe_w0", "safe_w05", "safe_w2", "safe_w10"]


def load(directory: Path) -> dict[str, list[dict]]:
    policies = {}
    for path in sorted(directory.glob("*_episodes.csv")):
        with path.open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if rows:
            policies[rows[0]["policy"]] = rows
    return policies


def summarize(rows: list[dict]) -> dict[str, dict]:
    """목표 이름별 건수. 비율은 내지 않고 분자와 분모를 그대로 둔다."""
    out = {}
    for name, _ in TARGETS:
        group = [r for r in rows if r["target_name"] == name]
        if not group:
            continue
        reached = [r for r in group if int(r["first_success_step"]) >= 0]
        entered = [r for r in group if r["entered_forbidden"] == "1"]
        out[name] = {
            "n": len(group),
            "reached": len(reached),
            "entered": len(entered),
            "entered_whole_horizon": sum(r["entered_forbidden_whole_horizon"] == "1" for r in group),
            "median_min_err": statistics.median(float(r["min_pos_err"]) for r in group),
            "median_final_err": statistics.median(float(r["final_pos_err"]) for r in group),
            "median_steps_inside": statistics.median(int(r["steps_inside"]) for r in entered) if entered else None,
        }
    return out


def ordered(policies: dict) -> list[str]:
    known = [p for p in POLICY_ORDER if p in policies]
    return known + sorted(p for p in policies if p not in POLICY_ORDER)


def render(policies: dict[str, list[dict]], key: str, markdown: bool) -> str:
    """key: 'entered'(첫 성공까지 금지 구역 진입), 'entered_whole_horizon', 'reached', 'err'."""
    names = ordered(policies)
    summaries = {p: summarize(policies[p]) for p in names}
    lines = []
    header = ["목표", *names]
    if markdown:
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
    else:
        lines.append("  ".join(f"{h:<26}" if i == 0 else f"{h:>10}" for i, h in enumerate(header)))
    for name, label in TARGETS:
        cells = []
        for p in names:
            s = summaries[p].get(name)
            if s is None:
                cells.append("-")
            elif key == "err":
                cells.append(f"{s['median_min_err']:.3f}")
            else:
                cells.append(f"{s[key]}/{s['n']}")
        if markdown:
            lines.append("| " + " | ".join([label, *cells]) + " |")
        else:
            lines.append("  ".join([f"{label:<26}", *[f"{c:>10}" for c in cells]]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="정책 단독 평가 결과 비교")
    parser.add_argument("--dir", type=Path, default=Path("results/policy_eval"))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)

    policies = load(args.dir)
    if not policies:
        raise SystemExit(f"{args.dir}에 *_episodes.csv가 없다.")
    sections = [
        ("금지 구역 진입 건수 (첫 성공 시점까지)", "entered"),
        ("금지 구역 진입 건수 (기록 구간 5초 전체, 참고용)", "entered_whole_horizon"),
        ("도달 건수 (위치와 자세 기준을 함께 만족)", "reached"),
        ("최소 위치 오차 중앙값 [m]", "err"),
    ]
    for title, key in sections:
        print()
        print(("### " if args.markdown else "") + title)
        if args.markdown:
            print()
        print(render(policies, key, args.markdown))


if __name__ == "__main__":
    main()
