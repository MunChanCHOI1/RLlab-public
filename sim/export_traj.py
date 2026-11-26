"""평가 궤적(*_traj.pt)을 torch 없이 읽을 수 있는 npz로 내보낸다.

사용 (Isaac Lab 폴더에서, torch가 있는 환경):
    uv run python <RLlab>/sim/export_traj.py --repo <RLlab>

results/policy_eval*/ 와 results/physical*/ 의 *_traj.pt를 읽어
results/analytics/traj_<평가>_<정책>.npz 로 저장한다. 시뮬레이터는 쓰지 않는다.

npz 내용:
    traj_b    (스텝+1, 환경, 3) float32, 로봇 베이스 기준 팔 끝(panda_hand 원점) 위치 [m]
    pos_err   (스텝+1, 환경) float32, 목표까지 위치 오차 [m]
    names     (환경,) 목표 이름 (zone_a, zone_b, zone_x, probe_below ...)
    targets   (환경, 3) 목표 위치 [m]
    step_dt   기록 간격 [s]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

GROUPS = {"policy_eval": "policy", "policy_eval_seeds": "policy",
          "physical": "physical", "physical_seeds": "physical"}


def main() -> None:
    parser = argparse.ArgumentParser(description="*_traj.pt -> npz")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--policies", nargs="+", default=["safe_w0", "safe_w2"],
                        help="정책 이름 접두어 (시드 접미어 _s1 등은 자동 포함)")
    args = parser.parse_args()
    out = args.repo / "results" / "analytics"
    out.mkdir(parents=True, exist_ok=True)
    for folder, kind in GROUPS.items():
        for path in sorted((args.repo / "results" / folder).glob("*_traj.pt")):
            tag = path.name[: -len("_traj.pt")]
            if not any(tag == p or tag.startswith(p + "_s") for p in args.policies):
                continue
            data = torch.load(path, map_location="cpu", weights_only=False)
            traj = data["traj_b"].numpy().astype(np.float32)
            pos = data["pos_err"].numpy().astype(np.float32)
            targets = np.asarray(data["targets"], dtype=np.float32)
            dest = out / f"traj_{kind}_{tag}.npz"
            np.savez_compressed(dest, traj_b=traj, pos_err=pos, names=np.asarray(data["names"]),
                                targets=targets, step_dt=np.float32(data["step_dt"]))
            print(f"{path.relative_to(args.repo)} -> {dest.relative_to(args.repo)}  traj {traj.shape}")


if __name__ == "__main__":
    main()
