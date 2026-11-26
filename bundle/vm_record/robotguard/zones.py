"""구역 판정. 의존성 없는 순수 파이썬이라 시뮬레이터 없이 테스트할 수 있다.

시뮬레이션 평가 스크립트(sim/eval_policy.py)는 같은 판정을 텐서로 계산하고,
시작할 때 이 함수와 결과가 같은지 몇 개 점으로 확인한다.
"""

from __future__ import annotations

from collections.abc import Sequence


def inside_zone(point: Sequence[float], zone: dict) -> bool:
    """점이 구역 상자 안에 있는가. 경계는 밖으로 본다 (모든 축에서 |p - c| < h)."""
    return all(abs(p - c) < h for p, c, h in zip(point, zone["center"], zone["half_size"]))


def distance_to_zone(point: Sequence[float], zone: dict) -> float:
    """점에서 구역 상자까지의 거리. 상자 안이면 0."""
    outside = [max(abs(p - c) - h, 0.0) for p, c, h in zip(point, zone["center"], zone["half_size"])]
    return sum(d * d for d in outside) ** 0.5


def forbidden_zones(scene: dict) -> list[dict]:
    return [z for z in scene["zones"] if not z["allowed"]]
