녹화 묶음 (VM용)
================

만든 시각: 2026-11-25T04:28:55Z
Isaac Lab 커밋: 99a3acd776f47fbcece4413f3c1d63f02b6979e2 (로컬에서 학습, 평가, Newton 녹화를 확인한 커밋)

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
