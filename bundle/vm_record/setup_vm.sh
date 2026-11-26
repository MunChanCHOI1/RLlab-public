#!/usr/bin/env bash
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

COMMIT="99a3acd776f47fbcece4413f3c1d63f02b6979e2"
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
