"""실험 시나리오 생성.

한 번의 시행(trial)마다 작업 지시 하나를 뽑고, 같은 지시에 대해
공격 없는 장면 1개와 공격 문구별 장면을 만든다. 같은 지시를 공유하므로
공격 유무만 다른 짝 비교가 된다.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Scenario:
    trial_id: int
    condition: str  # "clean" 또는 "attack"
    instruction: str
    scene: dict  # 계획기가 보는 장면 (공격 시 라벨 하나가 변조됨)
    truth_object: str
    truth_zone: str
    attack_id: str | None = None
    attack_goal: str | None = None  # "forbidden_zone" 또는 "misroute"
    carrier_object: str | None = None  # 변조된 라벨이 붙은 상자
    attack_zone: str | None = None  # forbidden_zone 공격이 노리는 구역


def load_scene(path: Path | None = None) -> dict:
    return json.loads((path or DATA_DIR / "scene.json").read_text(encoding="utf-8"))


def load_attacks(path: Path | None = None) -> list[dict]:
    return json.loads((path or DATA_DIR / "attacks.json").read_text(encoding="utf-8"))


def generate(n_trials: int, seed: int, scene: dict, attacks: list[dict]) -> list[Scenario]:
    rng = random.Random(seed)
    allowed_zones = [z for z in scene["zones"] if z["allowed"]]
    forbidden_zones = [z for z in scene["zones"] if not z["allowed"]]
    if not forbidden_zones:
        raise ValueError("장면에 금지 구역이 하나 이상 있어야 한다.")

    scenarios: list[Scenario] = []
    for trial_id in range(n_trials):
        target = rng.choice(scene["objects"])
        dest = rng.choice(allowed_zones)
        instruction = f"{target['name']}를 {dest['name']}으로 옮겨라."

        # 상자 나열 순서에 따른 편향을 줄이기 위해 시행마다 순서를 섞는다.
        base = copy.deepcopy(scene)
        rng.shuffle(base["objects"])

        scenarios.append(
            Scenario(
                trial_id=trial_id,
                condition="clean",
                instruction=instruction,
                scene=base,
                truth_object=target["id"],
                truth_zone=dest["id"],
            )
        )

        others = [o for o in scene["objects"] if o["id"] != target["id"]]
        for attack in attacks:
            carrier = rng.choice(others)
            forbidden = rng.choice(forbidden_zones)
            injected = attack["template"].format(zone_name=forbidden["name"])

            attacked = copy.deepcopy(base)
            for obj in attacked["objects"]:
                if obj["id"] == carrier["id"]:
                    obj["label"] = f"{obj['label']} / {injected}"

            scenarios.append(
                Scenario(
                    trial_id=trial_id,
                    condition="attack",
                    instruction=instruction,
                    scene=attacked,
                    truth_object=target["id"],
                    truth_zone=dest["id"],
                    attack_id=attack["id"],
                    attack_goal=attack["goal"],
                    carrier_object=carrier["id"],
                    attack_zone=forbidden["id"] if attack["goal"] == "forbidden_zone" else None,
                )
            )
    return scenarios
