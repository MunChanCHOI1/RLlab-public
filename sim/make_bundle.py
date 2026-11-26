"""VM에 가져갈 녹화 묶음을 만든다: 정책 두 개의 체크포인트와 설정, 장면, 재생 코드, 실행 스크립트.

사용: python sim/make_bundle.py [--lab C:/dev/repos/IsaacLab] [--out bundle/vm_record]

체크포인트는 Isaac Lab 학습 로그 폴더에 있고 이름이 모두 model_999.pt라서, 정책 이름별 폴더로
옮겨 담고 SHA-256과 Isaac Lab 커밋을 MANIFEST.json에 적는다. 넣을 파일을 하나씩 지정하므로
.env 같은 비밀 값은 들어가지 않고, 끝에 한 번 더 확인한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 정책 이름과 학습 실행 폴더 (docs/RESULTS.md의 정책 표와 같다).
POLICIES = {
    "safe_w0": ("reach_franka_safe_w0/2026-11-24_21-24-26", "대조군: 목표 혼합과 성공 조건만 적용, 벌점 가중치 0"),
    "safe_w2": ("reach_franka_safe_w2/2026-11-24_21-44-57", "벌점 정책: 금지 구역 벌점 가중치 2"),
}
CODE_FILES = ["sim/record_clip.py", "robotguard/__init__.py", "robotguard/zones.py", "data/scene.json"]

RECORD_SH = r"""#!/usr/bin/env bash
# 대조군(safe_w0)과 벌점 정책(safe_w2)을 같은 시작 자세와 목표로 재생해 영상을 남긴다 (Linux VM용).
#
#   ISAACLAB_DIR=~/IsaacLab ./record_pair.sh            # 본 촬영: 정책 2개 x 목표 2개
#   ISAACLAB_DIR=~/IsaacLab SMOKE=1 ./record_pair.sh    # 먼저 짧은 클립 1개로 화면 확인
#
# 환경 변수: SOURCE(기본 viz:kit), TARGETS(기본 "zone_b zone_x"), OUT(기본 ./out),
#            STEP_OFFSET(기본 viz:kit이면 5: 렌더러가 준비될 때까지 앞의 5스텝을 건너뜀)
set -euo pipefail

BUNDLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="${ISAACLAB_DIR:?ISAACLAB_DIR에 IsaacLab 폴더를 지정한다}"
SOURCE="${SOURCE:-viz:kit}"
TARGETS="${TARGETS:-zone_b zone_x}"
OUT="${OUT:-$BUNDLE/out}"
EXPECTED_COMMIT="__ISAACLAB_COMMIT__"

(cd "$BUNDLE" && sha256sum -c SHA256SUMS --quiet) || { echo "묶음 파일의 해시가 맞지 않는다."; exit 1; }

ACTUAL_COMMIT="$(git -C "$LAB" rev-parse HEAD)"
if [ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT" ]; then
  echo "주의: IsaacLab 커밋이 로컬에서 확인한 것과 다르다."
  echo "  기대: $EXPECTED_COMMIT"
  echo "  실제: $ACTUAL_COMMIT"
  echo "  맞추려면: git -C \"$LAB\" checkout $EXPECTED_COMMIT"
  [ "${ALLOW_OTHER_COMMIT:-0}" = "1" ] || exit 1
fi

EXTRAS=(--extra video)
if [ "$SOURCE" = "viz:kit" ]; then
  # Isaac Sim은 처음 실행할 때 NVIDIA Omniverse EULA 동의를 묻는다. 동의는 사용자가 직접 한다.
  if [ -z "${OMNI_KIT_ACCEPT_EULA:-}" ]; then
    echo "Isaac Sim을 쓰려면 NVIDIA Omniverse EULA에 동의해야 한다."
    echo "약관을 읽고 동의한다면 직접 실행한다:  export OMNI_KIT_ACCEPT_EULA=yes"
    exit 1
  fi
  EXTRAS+=(--extra isaacsim)
  STEP_OFFSET="${STEP_OFFSET:-5}"
else
  STEP_OFFSET="${STEP_OFFSET:-0}"
fi

mkdir -p "$OUT"
cd "$LAB"

run_clip() {  # 정책 이름, 목표 구역, 스텝 수
  uv run "${EXTRAS[@]}" python "$BUNDLE/sim/record_clip.py" \
    --checkpoint "$BUNDLE/policies/$1/model_999.pt" --tag "$1" --target "$2" \
    --source "$SOURCE" --steps "$3" --step_offset "$STEP_OFFSET" --out "$OUT" \
    2>&1 | tee "$OUT/${1}_${2}_run.log"
}

if [ "${SMOKE:-0}" = "1" ]; then
  run_clip safe_w2 zone_x 60
  echo "확인할 것: $OUT 의 mp4에서 팔, 목표 좌표축, 구역 윤곽선(초록 2개, 빨강 1개)이 보이는가."
  exit 0
fi

for target in $TARGETS; do
  for tag in safe_w0 safe_w2; do
    run_clip "$tag" "$target" 150
  done
done
echo "끝. 내려받을 것: $OUT 의 *.mp4 와 *.json (reference/ 의 로컬 측정값과 비교한다)."
"""

SETUP_SH = r"""#!/usr/bin/env bash
# VM 준비: 자동 종료 예약, GPU 드라이버, 시스템 패키지, uv, IsaacLab(고정 커밋), 의존성 설치.
# 여러 번 실행해도 된다. 드라이버 설치 뒤 재부팅하면 다시 실행한다.
#
#   ./setup_vm.sh
#
# 환경 변수: AUTO_SHUTDOWN_MIN(기본 300: 이 시간 뒤 VM을 끈다. 0이면 예약하지 않음),
#            ISAACLAB_DIR(기본 ~/IsaacLab)
# 2026-11-25에 GCP g2-standard-8 + L4, Ubuntu 24.04(커널 7.0.0-1017-gcp)에서 실행했다.
# 드라이버 단계는 그때 손으로 실행한 명령을 옮겨 적은 것이라, 이 스크립트로는 다시 돌려 보지 않았다.
set -euo pipefail

COMMIT="__ISAACLAB_COMMIT__"
MIN_DRIVER="595.58.03"   # Isaac Lab 설치 문서가 적은 Linux x86_64 드라이버
LAB="${ISAACLAB_DIR:-$HOME/IsaacLab}"
AUTO_SHUTDOWN_MIN="${AUTO_SHUTDOWN_MIN:-300}"

# 0. 깜빡하고 켜 둔 채로 두지 않도록 자동 종료를 먼저 예약한다 (종료된 VM은 GPU 요금이 나오지 않는다).
if [ "$AUTO_SHUTDOWN_MIN" != "0" ]; then
  sudo shutdown -h "+$AUTO_SHUTDOWN_MIN" "RLlab: auto shutdown" || true
  echo "자동 종료 예약: ${AUTO_SHUTDOWN_MIN}분 뒤. 취소: sudo shutdown -c"
fi

# 1. GPU 드라이버
if ! command -v nvidia-smi >/dev/null 2>&1; then
  # Google의 install_gpu_driver.py는 550.54.15를 넣는데, Ubuntu 24.04 이미지의 커널(7.0)에서
  # 모듈 빌드가 실패했고 버전도 기준보다 낮다 (2026-11-25 확인). Ubuntu 저장소의 595 드라이버와
  # 지금 커널용으로 미리 빌드된 모듈을 쓴다.
  echo "NVIDIA 드라이버가 없다. Ubuntu 저장소의 595 서버 드라이버를 설치한다."
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    "linux-modules-nvidia-595-server-$(uname -r)" nvidia-driver-595-server
  sudo modprobe nvidia
fi
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
if [ "$(printf '%s\n%s\n' "$MIN_DRIVER" "$DRIVER" | sort -V | head -1)" != "$MIN_DRIVER" ]; then
  echo "주의: 드라이버 $DRIVER 가 문서의 $MIN_DRIVER 보다 낮다. Isaac Sim이 뜨지 않을 수 있다."
  echo "  이 경우 NVIDIA의 $MIN_DRIVER 이상 드라이버로 바꾼 뒤 다시 실행한다."
  [ "${ALLOW_OLD_DRIVER:-0}" = "1" ] || exit 1
fi

# 2. 시스템 패키지 (없는 이름은 건너뛰고 알려 준다)
sudo apt-get update -y
for pkg in git curl libgl1 libglu1-mesa libegl1 libxt6 libxrandr2 libxcursor1 libxi6 libxinerama1 libx11-6 libvulkan1; do
  sudo apt-get install -y "$pkg" >/dev/null 2>&1 || echo "  건너뜀(설치 실패): $pkg"
done

# 3. uv (Isaac Lab 설치 문서의 방법)
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

# 4. IsaacLab을 로컬에서 확인한 커밋으로 받는다
if [ ! -d "$LAB/.git" ]; then
  git clone https://github.com/isaac-sim/IsaacLab.git "$LAB"
fi
git -C "$LAB" fetch --quiet origin
git -C "$LAB" checkout --quiet "$COMMIT"
echo "IsaacLab 커밋: $(git -C "$LAB" rev-parse HEAD)"

# 5. 의존성 (Isaac Sim 포함, 용량이 크고 오래 걸린다)
cd "$LAB"
uv sync --extra isaacsim --extra video
df -h "$HOME" | tail -1

echo
echo "준비 끝. 다음:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo "  export OMNI_KIT_ACCEPT_EULA=yes     # NVIDIA Omniverse EULA를 읽고 동의하는 경우에만, 직접"
echo "  ISAACLAB_DIR=$LAB SMOKE=1 ./record_pair.sh"
"""

README = """녹화 묶음 (VM용)
================

만든 시각: {created}
Isaac Lab 커밋: {commit} (로컬에서 학습, 평가, Newton 녹화를 확인한 커밋)

담긴 것
  policies/safe_w0, policies/safe_w2   체크포인트(model_999.pt)와 학습 설정(agent.yaml, env.yaml)
  sim/record_clip.py                   녹화용 재생 코드
  robotguard/zones.py, data/scene.json 금지 구역 판정과 장면 좌표
  reference/                           이 PC에서 Newton 화면으로 같은 재생을 했을 때의 측정값(JSON)
  setup_vm.sh                          VM 준비 (자동 종료 예약, 드라이버, uv, IsaacLab 고정 커밋, 의존성)
  record_pair.sh                       녹화 실행 스크립트
  MANIFEST.json, SHA256SUMS            파일 목록과 해시

VM에서
  1. 묶음을 올리고 푼 뒤 해시를 확인한다:  tar xzf vm_record.tar.gz && cd vm_record && sha256sum -c SHA256SUMS
  2. VM을 준비한다:                       chmod +x *.sh && ./setup_vm.sh
     (5시간 뒤 자동 종료를 예약한다. 드라이버 설치 뒤 재부팅했으면 다시 실행한다)
  3. NVIDIA Omniverse EULA를 읽고 동의하면: export OMNI_KIT_ACCEPT_EULA=yes
  4. 짧은 클립 1개로 화면을 확인한다:      ISAACLAB_DIR=~/IsaacLab SMOKE=1 ./record_pair.sh
  5. 본 촬영:                             ISAACLAB_DIR=~/IsaacLab ./record_pair.sh
  6. out/ 의 mp4와 json을 내려받고, json의 측정값을 reference/ 와 비교한다.
  7. VM과 디스크를 삭제한다.

알아둘 것
  - 영상은 "대표 재생 영상"이다. 결과 표를 만든 에피소드를 다시 튼 것이 아니라, 같은 정책을
    정해진 시작 자세(로봇 기본 자세)와 목표(구역 중심, 고정된 목표 자세)로 새로 한 번 돌린 것이다.
  - viz:kit에서는 렌더러 준비를 위해 앞의 5스텝(0.17초)을 건너뛰고 녹화한다. 측정값(JSON)은
    0스텝부터 계산하므로, 영상의 첫 프레임은 측정 구간의 5스텝째다.
  - reference/ 의 값과 VM의 값이 다르면 물리 결과가 달라진 것이므로 영상 설명에 VM의 값을 쓴다.
  - 이 묶음에는 API 키나 .env가 들어 있지 않다.
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="VM용 녹화 묶음 만들기")
    parser.add_argument("--lab", type=Path, default=Path("C:/dev/repos/IsaacLab"))
    parser.add_argument("--out", type=Path, default=REPO / "bundle" / "vm_record")
    parser.add_argument("--reference", type=Path, default=REPO / "results" / "video",
                        help="로컬 녹화의 측정값 JSON이 있는 폴더")
    args = parser.parse_args(argv)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.lab, capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=args.lab,
                           capture_output=True, text=True, check=True).stdout.strip()

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    sources: dict[str, str] = {}

    def put(src: Path, rel: str) -> None:
        if not src.is_file():
            raise SystemExit(f"파일이 없다: {src}")
        dest = args.out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        sources[rel] = str(src)

    for name, (run_dir, _) in POLICIES.items():
        run = args.lab / "logs" / "rsl_rl" / run_dir
        put(run / "model_999.pt", f"policies/{name}/model_999.pt")
        put(run / "params" / "agent.yaml", f"policies/{name}/params/agent.yaml")
        put(run / "params" / "env.yaml", f"policies/{name}/params/env.yaml")
    for rel in CODE_FILES:
        put(REPO / rel, rel)
    references = sorted(args.reference.glob("*.json")) if args.reference.is_dir() else []
    for ref in references:
        put(ref, f"reference/{ref.name}")

    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (args.out / "record_pair.sh").write_text(RECORD_SH.replace("__ISAACLAB_COMMIT__", commit),
                                             encoding="utf-8", newline="\n")
    (args.out / "setup_vm.sh").write_text(SETUP_SH.replace("__ISAACLAB_COMMIT__", commit),
                                          encoding="utf-8", newline="\n")
    (args.out / "README.txt").write_text(README.format(created=created, commit=commit),
                                         encoding="utf-8", newline="\n")

    files = sorted(p for p in args.out.rglob("*") if p.is_file())
    leaked = [p for p in files if p.name.startswith(".env")]
    if leaked:
        raise SystemExit(f"비밀 값 파일이 묶음에 들어갔다: {leaked}")
    entries = [{"path": p.relative_to(args.out).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p),
                "source": sources.get(p.relative_to(args.out).as_posix())} for p in files]
    (args.out / "SHA256SUMS").write_text("".join(f"{e['sha256']}  {e['path']}\n" for e in entries),
                                         encoding="utf-8", newline="\n")
    manifest = {
        "created_utc": created,
        "isaaclab_commit": commit,
        "isaaclab_tracked_files_modified": bool(dirty),
        "task": "Isaac-Reach-Franka (play 모드)",
        "policies": {name: {"description": desc, "run_dir": run_dir} for name, (run_dir, desc) in POLICIES.items()},
        "reference_note": "reference/ 는 이 PC에서 viz:newton으로 같은 재생을 했을 때의 측정값이다.",
        "files": entries,
    }
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                            encoding="utf-8", newline="\n")

    print(f"묶음: {args.out}")
    print(f"Isaac Lab 커밋: {commit}" + (" (추적 파일에 수정 있음)" if dirty else ""))
    for e in entries:
        print(f"  {e['sha256'][:12]}  {e['bytes']:>8}  {e['path']}")
    if not references:
        print("주의: reference/ 가 비어 있다. 먼저 sim/record_pair.ps1로 로컬 녹화를 한다.")


if __name__ == "__main__":
    main()
