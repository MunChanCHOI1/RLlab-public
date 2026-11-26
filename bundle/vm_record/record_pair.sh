#!/usr/bin/env bash
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
EXPECTED_COMMIT="99a3acd776f47fbcece4413f3c1d63f02b6979e2"

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
