"""결과의 근거가 되는 체크포인트를 Isaac Lab 학습 로그 폴더에서 이 저장소로 복사해 둔다.

사용: python sim/archive_checkpoints.py [--lab C:/dev/repos/IsaacLab] [--out checkpoints]

학습 로그 폴더에는 체크포인트가 모두 model_999.pt라는 이름으로 있고 저장소 밖이라서,
그 폴더를 지우면 결과를 재현할 수 없다. 정책 이름별 폴더에 체크포인트와 학습 설정을 담고,
MANIFEST.json에 원래 위치, 학습 시드, SHA-256, Isaac Lab 커밋을 적는다.
시드 반복 학습(sim/run_seed_batch.ps1)이 남긴 results/train/seed_runs.csv가 있으면 그 정책도 함께 담는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 정책 이름: (학습 실행 폴더, 과제, 학습 시드). docs/RESULTS.md의 정책 표와 같다.
BASE_POLICIES = {
    "baseline": ("reach_franka/2026-11-24_21-02-13", "Isaac-Reach-Franka", 42),
    "safe_w0": ("reach_franka_safe_w0/2026-11-24_21-24-26", "RLlab-Reach-Franka-Safe-W0", 42),
    "safe_w05": ("reach_franka_safe_w05/2026-11-24_21-34-43", "RLlab-Reach-Franka-Safe-W05", 42),
    "safe_w2": ("reach_franka_safe_w2/2026-11-24_21-44-57", "RLlab-Reach-Franka-Safe-W2", 42),
    "safe_w10": ("reach_franka_safe_w10/2026-11-24_21-56-25", "RLlab-Reach-Franka-Safe-W10", 42),
}
FILES = ["model_999.pt", "params/agent.yaml", "params/env.yaml"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yaml_seed(path: Path) -> int | None:
    """agent.yaml의 첫 번째 최상위 seed 값을 읽는다 (적어 둔 시드와 대조하기 위한 것)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("seed:"):
            return int(line.split(":", 1)[1])
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="체크포인트를 저장소에 보관")
    parser.add_argument("--lab", type=Path, default=Path("C:/dev/repos/IsaacLab"))
    parser.add_argument("--out", type=Path, default=REPO / "checkpoints")
    parser.add_argument("--seed_runs", type=Path, default=REPO / "results" / "train" / "seed_runs.csv")
    args = parser.parse_args(argv)

    policies = {name: (args.lab / "logs" / "rsl_rl" / run, task, seed)
                for name, (run, task, seed) in BASE_POLICIES.items()}
    if args.seed_runs.exists():
        with args.seed_runs.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                policies[row["policy"]] = (Path(row["run_dir"]), f"RLlab-Reach-Franka-Safe-{row['variant']}",
                                           int(row["seed"]))

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.lab, capture_output=True, text=True,
                            check=True).stdout.strip()
    entries = {}
    for name, (run, task, seed) in policies.items():
        recorded = yaml_seed(run / "params" / "agent.yaml")
        if recorded != seed:
            raise SystemExit(f"{name}: 적어 둔 시드({seed})와 학습 설정의 시드({recorded})가 다르다.")
        files = {}
        for rel in FILES:
            src = run / rel
            if not src.is_file():
                raise SystemExit(f"파일이 없다: {src}")
            dest = args.out / name / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            files[rel] = {"bytes": dest.stat().st_size, "sha256": sha256(dest)}
        entries[name] = {"task": task, "train_seed": seed, "source_run_dir": str(run), "files": files}

    manifest = {"isaaclab_commit": commit, "train": "rsl_rl PPO, 환경 4096개, 1000회 반복", "policies": entries}
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"보관: {args.out} (정책 {len(entries)}개, Isaac Lab 커밋 {commit[:7]})")
    for name, e in entries.items():
        print(f"  {name:<14} 시드 {e['train_seed']:<3} {e['files']['model_999.pt']['sha256'][:12]}")


if __name__ == "__main__":
    main()
