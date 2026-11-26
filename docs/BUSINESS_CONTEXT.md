# 비즈니스 맥락: LLM 기반 Physical AI의 다계층 리스크 통제

이 문서는 실험 결과를 외부 기준(보안 표준, 위험관리 프레임워크, 규제)과 산업 동향에 연결하고, 기업이 쓸 통제 모델로 옮겨 적었습니다. 수치는 [README](../README.md), [RESULTS.md](RESULTS.md), [REPORT.md](REPORT.md)에 있는 값만 썼습니다. 외부 자료는 모두 2026-11-25에 원문을 확인했고 출처는 끝에 있습니다.

## 1. 데스크 리서치: 이 문제가 외부 기준에서 어디에 있는가

### 1.1 보안: OWASP Top 10 for LLM Applications

- **LLM01:2025 Prompt Injection.** OWASP는 입력이 LLM의 동작이나 출력을 의도하지 않은 방향으로 바꾸는 것을 프롬프트 인젝션으로 정의하고, 웹사이트나 파일 같은 외부 콘텐츠에 심은 지시가 모델에 들어가는 경우를 **간접(indirect) 인젝션**으로 구분합니다 [R1]. 상자 라벨은 사용자가 아닌 제3자가 넣은 외부 콘텐츠이므로 이 실험의 공격은 간접 인젝션에 해당합니다.
- OWASP가 제시하는 완화책 가운데 이 실험의 계층과 겹치는 것은 외부 콘텐츠 분리(D1), 출력 형식 정의와 검증(JSON 계획 + D2), 고위험 행동에 대한 사람 승인(D3), 적대적 테스트(가정 조건 평가)입니다 [R1].
- **LLM06:2025 Excessive Agency.** LLM이 조작된 출력에 따라 피해를 주는 행동을 할 수 있는 상태를 말하며, 원인을 과도한 기능, 권한, 자율성으로 나눕니다. 완화책으로 고영향 행동의 사람 승인과, 허용 여부를 LLM에 맡기지 말고 하위 시스템에서 권한을 강제하라는 원칙(complete mediation)을 둡니다 [R2]. 로봇팔을 움직이는 계획기는 물리적 행동 권한을 가진 에이전트이므로, D2(코드가 강제하는 금지 구역 차단)가 이 원칙을 그대로 구현합니다.
- OWASP는 2026년판 목록도 공개했습니다. 2026년판에서도 Prompt Injection은 LLM01이고, Excessive Agency는 LLM03으로 올라갔습니다 [R3]. 에이전트 전용 목록(Top 10 for Agentic Applications 2026)은 ASI01을 Agent Goal Hijack으로 둡니다 [R4]. 이 문서의 세부 설명은 원문을 확인한 2025년판 기준입니다.

### 1.2 위험관리: NIST AI RMF 1.0과 생성형 AI 프로파일

- **NIST AI RMF 1.0** (2023년 1월)은 위험관리를 네 기능으로 나눕니다 [R5][R6].
  - **Govern**: 조직 전반에 위험관리 문화와 책임 체계를 세우는, 나머지 기능에 걸친 기능
  - **Map**: AI 시스템의 사용 맥락을 정리해 위험을 정의
  - **Measure**: 정량, 정성 방법으로 위험을 분석, 평가, 벤치마크, 모니터링
  - **Manage**: 식별되고 측정된 위험에 자원을 배분하고 대응
- 이 실험은 주로 **Map**(위협 모델: 공격자는 라벨만 붙일 수 있음)과 **Measure**(계층별 건수와 분모, 학습 시드 반복)에 해당하고, 계층별 잔여 위험을 보고 통제를 고르는 일이 **Manage**에 해당합니다.
- **NIST AI 600-1 생성형 AI 프로파일** (2024년 7월)은 정보보안 위험 항목(2.9절)에서 직접 인젝션과 간접 인젝션을 구분해 설명합니다. 간접 인젝션은 직접 인터페이스 없이, 시스템이 가져올 데이터에 지시를 심어 LLM 연동 애플리케이션을 공격하는 방식으로 적혀 있습니다. 권고 조치에는 레드팀과 적대적 역할극 같은 테스트가 들어 있습니다 [R7].

### 1.3 규제: EU AI Act (Digital Omnibus 개정 반영)

- **고위험 분류(제6조 제1항).** AI 시스템이 부속서 I의 EU 조화 법령이 적용되는 제품의 안전 구성요소이거나 그 자체가 제품이고, 그 제품이 제3자 적합성 평가를 받아야 하면 고위험으로 분류됩니다 [R8].
- **기계류는 2026년 개정으로 경로가 바뀌었습니다.** Digital Omnibus on AI(Regulation (EU) 2026/1744, 2026-07-08 채택, 관보 게재 2026-07-24, 2026-07-27 발효)는 기계류 규정(Regulation (EU) 2023/1230)을 부속서 I의 Section A에서 Section B로 옮겨 "부문별 접근"으로 바꿨습니다. 대신 기계류 규정 부속서 III에 고위험 AI 요건을 반영하는 위임법을 집행위원회가 채택하도록 했고, 그 요건은 AI Act 제3장 제2절(제8조~제15조)과 제17, 19, 72, 73조의 내용을 반영해야 하며 2028-08-02까지 적용되도록 정했습니다 [R9][R10][R11]. 즉 로봇 셀 같은 기계에 들어가는 AI는 AI Act를 직접 적용받기보다 기계류 규정으로 같은 수준의 요건을 맞추게 됩니다.
- **적용 시점.** 개정 후 고위험 의무(제3장 제1~3절)는 부속서 III 고위험 시스템에 2027-12-02부터, 제6조 제1항과 부속서 I 고위험 시스템에 2028-08-02부터 적용됩니다 [R9][R12]. 원래 일정은 2026-08-02 일반 적용이었습니다 [R12]. 기계류 규정 자체는 2027-01-20부터 적용됩니다.
- **제14조 인적 감독.** 고위험 AI는 사람이 효과적으로 감독할 수 있게 설계해야 하며, 감독자가 시스템의 한계를 이해하고, 자동화 편향을 인식하고, 출력을 무시하거나 뒤집고, 정지 버튼 등으로 개입하거나 안전하게 멈출 수 있어야 합니다 [R13]. D3의 승인 요청이 이 요건의 일부(개입 지점)에 해당합니다.
- **제15조 정확성, 견고성, 사이버보안.** 오류와 불일치에 대한 회복력, 백업이나 페일세이프 같은 기술적 중복, 그리고 권한 없는 제3자가 취약점을 이용해 사용, 출력, 성능을 바꾸려는 시도에 대한 저항을 요구합니다 [R14]. 라벨 공격은 "권한 없는 제3자의 출력 변경 시도"이고, 벌점 정책은 상위 계층이 뚫렸을 때를 위한 기술적 중복에 해당합니다.

### 1.4 산업 동향: NVIDIA Physical AI와 디지털 트윈

- NVIDIA는 Isaac Sim을 Omniverse 라이브러리 위에 만든 오픈소스 참조 프레임워크로, 로봇의 시뮬레이션, 테스트, 합성 데이터 생성에 쓰는 도구로 설명하고, Isaac Lab을 Isaac Sim 위의 대규모 로봇 학습용 참조 애플리케이션으로 둡니다 [R15]. 이 실험의 정책 학습(Isaac Lab)과 대표 영상 렌더링(Isaac Sim)이 같은 도구 체계입니다.
- NVIDIA는 2025년 1월 공장과 창고의 디지털 트윈에서 로봇 군집을 실제 배치 전에 개발, 테스트, 최적화하는 참조 아키텍처 "Mega" Omniverse Blueprint를 발표했고, KION과 Accenture를 첫 사용처로 소개했습니다 [R16]. 2025년 4월 글에서는 Foxconn, Pegatron, Schaeffler 등을 사용 기업으로 들고, 배치 전 가상 환경에서 검증하는 것을 핵심 가치로 설명합니다 [R17].
- 정리하면, 산업 현장은 "가상 환경에서 먼저 검증하고 배치한다"로 가고 있고, 규제는 2027~2028년부터 견고성, 사이버보안, 인적 감독의 증거를 요구합니다. 이 실험은 그 사이의 질문, 즉 **디지털 트윈 안에서 AI 통제가 실제로 작동하는지를 어떻게 증거로 남길 것인가**에 대한 작은 예시입니다.

참고로 ISO/IEC 42001:2023은 조직의 AI 경영시스템(AIMS)을 수립, 운영, 개선하기 위한 요구사항을 정한 국제표준이며 인증은 선택입니다 [R18]. 아래 통제 모델은 이런 경영시스템 안에서 개별 AI 시스템의 통제 설계와 테스트에 해당하는 부분입니다.

## 2. 비즈니스 Use Case: 스마트 물류·제조 현장에 LLM 기반 Physical AI 도입 시 다계층 리스크 통제 모델

### 2.1 시나리오

| 구분 | 내용 |
|---|---|
| 현장 | 물류센터 또는 제조 라인의 분류, 적재 셀. 작업자가 자연어로 작업을 지시하면 LLM 계획기가 옮길 물건과 목적지를 정하고, 강화학습 정책이 로봇팔을 움직임 |
| 행위자 | 작업 지시자(신뢰), LLM 계획기(공급사 모델), 검사 단계(현장 시스템의 코드), 승인자(현장 관리자), 로봇 정책(학습된 제어기), 공격자 |
| 보호 자산 | 정비 중 구역의 작업자 안전, 설비, 출하 정확성(오배송 방지), 운영 연속성 |
| 위협 | 공격자는 모델, 프롬프트, 코드, 로봇에 접근하지 못하고 **물건에 라벨만 붙일 수 있음**. 라벨 글자는 스캐너를 거쳐 장면 정보로 들어감 |
| 공격 목표 | (1) 물건을 정비 중 구역으로 보내게 함 (2) 지시된 물건 대신 공격자의 물건을 옮기게 함 |

이 위협은 내부자 권한이나 해킹 없이, 협력사나 반입 물품으로 누구나 시도할 수 있으므로 현장 도입 시 먼저 따져야 할 시나리오입니다.

### 2.2 통제 프레임워크 매핑

| 계층 | 통제 유형 | 내부통제 비유 | 대응 기준 | 이 실험의 증거 | 관측된 잔여 위험 |
|---|---|---|---|---|---|
| **D0** 방어 없음 | 없음 (기준선) | 통제 부재 상태의 고유 위험 | OWASP LLM01 위협 정의, NIST Map | Claude 2종은 공격 반영 0/120, 로컬 qwen3:8b는 금지 구역 11/80, 오배송 30/40 (모델마다 1회) | 모델 선택에 따라 고유 위험이 크게 다름. 소형·로컬 모델을 쓰면 상위 통제가 필수 |
| **D1** 프롬프트 분리 | 예방, 자동, **소프트** (모델 판단에 의존) | 업무 지침 고지. 따르는 쪽의 판단에 맡기므로 단독으로 의존하기 어려운 통제 | OWASP LLM01 외부 콘텐츠 분리, NIST Manage | D0도 0건이라 D1만의 효과는 분리되지 않음 | 모델이 속으면 아무것도 막지 못함 (가정 조건에서 기본 정책 80/80 진입) |
| **D2** 금지 구역 차단 | 예방, 자동, **하드** (규칙대로 동작) | 애플리케이션 통제 (입력값 검증, 한도 통제) | OWASP LLM06 하위 시스템 권한 강제, EU AI Act 제15조 | 가정 조건에서 정책에 전달된 금지 목적지 80 → 0 | 목적지만 봄. 허용 목적지로 가는 도중 침범은 남음 (기본 정책 1/60, 대조군 0~9/60) |
| **D3** 지시 대조 + 승인 요청 | 적발과 예방, **수동 승인** | 승인 통제, maker-checker, 직무분리 | OWASP LLM01/LLM06 고위험 행동 사람 승인, EU AI Act 제14조 | 다른 상자를 고른 계획 40건 보류 (전달 60 → 20). 실제 LLM 실행에서 공격 없는 장면 20/20 통과, 오경보 0 | 승인 결과(사람이 거절했는지)는 미측정. 문자열 대조라 표현이 다른 지시문의 오경보 미측정. 승인 피로와 자동화 편향 |
| **Safe RL** 벌점 정책 | 예방, 자동, **확률적** (물리 계층) | 보완 통제, 최후 방어선. 상위 통제가 뚫리거나 못 보는 위험을 줄임 | EU AI Act 제15조 기술적 중복, NIST Measure (반복 시험) | 벌점 2, 학습 시드 4개: 검사 없이도 금지 목적지 0/80, 이동 중 침범 0/60, 허용 목적지 도달 60/60 | 보장이 아님. 구역 경계 4cm 아래 목표 0~10/64, 구역 안 무작위 목표 0~4/64. 멈춘 사실을 상위 계층에 알리지 않음 |

표에 더해, 체크포인트마다 학습 시드, sha256, Isaac Lab 커밋을 기록한 것(`checkpoints/MANIFEST.json`)은 IT 일반통제(ITGC)의 변경관리와 구성관리에 해당합니다. 어떤 정책이 시험되었고 어떤 정책이 배치되는지를 대조할 수 있어야 시험 결과가 증거가 됩니다.

### 2.3 읽는 법

- **하드 통제와 소프트 통제를 구분해야 합니다.** D1은 모델에게 부탁하는 통제입니다. Claude에서는 D0부터 0건이라 효과를 분리할 수 없었지만, qwen3:8b에서는 D1이 오배송 반영을 30/40에서 0/40으로 줄였습니다 ([MULTI_VENDOR.md](MULTI_VENDOR.md)). 그래도 모델의 판단에 기대는 통제라 보장은 아닙니다. D2는 규칙이라 "뚫렸다고 가정"한 입력 80건을 모두 막았습니다.
- **한 통제가 모든 위험을 덮지 않습니다.** D2는 목적지 위험을 막지만 경로 위험은 못 보고, 벌점 정책은 경로 위험까지 줄이지만 경계 근처에서 샙니다. 통제마다 덮는 위험과 남기는 위험을 따로 적어야 합니다.
- **"뚫렸다고 가정(assumed breach)"한 시험이 필요합니다.** 실제 LLM이 속지 않으면 뒤 통제는 한 번도 시험되지 않습니다. 상위 통제의 실패를 가정하고 하위 통제를 독립적으로 시험해야 각 통제의 운영 효과성을 말할 수 있습니다.

### 2.4 So What: 서비스 라인별 시사점

- **감사와 AI 보증(Assurance).** AI 시스템의 통제를 시험할 때 필요한 것은 "통제가 있다"가 아니라 통제별 분모와 건수, 반복 횟수, 해당 없음 규칙, 시험 대상과 배치 대상의 일치 증거입니다. 이 실험의 설계(계층별 지점 구분, 같은 응답에 검사만 바꾼 비교, 시드 반복, 해시 기록)는 AI 통제의 설계 효과성과 운영 효과성을 시험하는 절차의 축소판으로 쓸 수 있습니다.
- **컨설팅과 전략.** Physical AI 도입을 검토하는 고객에게는 투자 판단 전에 디지털 트윈에서 통제를 시험하는 단계를 넣을 수 있습니다. 이번 실험의 GCP 녹화는 L4 GPU VM 약 40분, 견적 기준 1달러 안팎으로 추정했고 실제 청구액은 확인하지 않았습니다. 학습은 노트북 GPU에서 했습니다. 이런 시험은 실제 설비 시험보다 훨씬 싸게, 배치 전에 할 수 있습니다.
- **규제 대응.** 기계에 들어가는 고위험 AI 요건은 2028-08-02까지 기계류 규정으로 반영될 예정입니다. 유럽에 설비를 수출하거나 운영하는 고객은 제14조(인적 감독)와 제15조(견고성, 사이버보안)에 대응하는 통제와 시험 증거를 지금부터 쌓을 수 있습니다.

### 2.5 고객이 이 프레임워크로 할 수 있는 일

1. **경로 목록화.** LLM 출력이 물리 행동으로 이어지는 경로와, 그 경로에 들어오는 외부 콘텐츠(라벨, 문서, 메일, 센서 텍스트)를 목록으로 만듭니다.
2. **통제 분류.** 각 경로의 통제를 소프트/하드, 예방/적발, 자동/수동으로 분류하고, 소프트 통제만 있는 고영향 경로를 먼저 찾습니다.
3. **가정 조건 시험.** 디지털 트윈에서 상위 계층이 뚫렸다고 가정하고 하위 통제를 하나씩 시험해, 계층별 잔여 위험을 건수로 적습니다.
4. **수용 기준 설정.** 남은 위험(예: 경계 근처 0~10/64)을 경영진이 수용할지, 통제를 더할지(팔 전체 판정, 거리 기반 벌점, 정지 사실 보고) 정합니다.
5. **증거 유지.** 시험한 모델과 정책의 버전, 해시, 시험 조건을 변경관리와 함께 남겨 재시험과 감사에 씁니다.

## 3. 한계

- **시뮬레이션만 했습니다.** 학습과 측정은 Newton(MJWarp) 물리, Isaac Sim은 대표 영상 네 개의 렌더링에만 썼습니다. 실제 로봇, 카메라 인식, 물건 집기는 없습니다.
- **과제가 하나입니다.** Franka 팔 끝을 목표 위치로 뻗는 도달 과제, 상자 모양 구역 세 개, 팔 끝 한 점 판정입니다.
- **Claude 모델은 공격을 따르지 않았습니다 (0/120, 두 모델 모두).** 로컬 qwen3:8b는 D0에서 따랐지만 이 계획을 물리 계층에 넣지는 않았습니다. 그래서 물리 계층의 결과는 모두 "계획기가 뚫렸다면"의 조건부 결과이며, 금지 목적지 80건은 측정값이 아니라 가정입니다. 0/120은 "안전하다"가 아니라 단순한 문구 6종, 같은 회사 모델 2개, 1회 실행에서 관측되지 않았다는 뜻입니다.
- **표본이 작습니다.** 벌점 2와 대조군은 학습 시드 4개, 다른 정책은 1개, 평가는 정책마다 1회입니다. 0건은 보장이 아닙니다.
- **D3의 사람 승인은 시험하지 않았습니다.** 관측한 것은 승인 요청이 나간 것까지입니다.
- **규제 해석은 법률 자문이 아닙니다.** 기준 조항과의 대응은 통제 설계의 방향을 보이기 위한 것이며, 특정 제품의 고위험 해당 여부나 적합성 판단은 별도 검토가 필요합니다.

## 참고문헌

모두 2026-11-25 접속.

- [R1] OWASP Gen AI Security Project, "LLM01:2025 Prompt Injection", 2025. https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- [R2] OWASP Gen AI Security Project, "LLM06:2025 Excessive Agency", 2025. https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
- [R3] OWASP Gen AI Security Project, "OWASP Top 10 for LLM Applications 2026" (목록 페이지), 2026. https://genai.owasp.org/top-10-for-llm-applications-2026/ ; 2025년판 목록: https://genai.owasp.org/llm-top-10/
- [R4] OWASP Gen AI Security Project, "Top 10 for Agentic Applications 2026", 2025~2026. https://genai.owasp.org/top-10-for-agentic-applications-2026/
- [R5] NIST, "Artificial Intelligence Risk Management Framework (AI RMF 1.0)", NIST AI 100-1, 2023. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- [R6] NIST, "AI Risk Management Framework" (안내 페이지), 2023~. https://www.nist.gov/itl/ai-risk-management-framework
- [R7] NIST, "Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile", NIST AI 600-1, 2024. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- [R8] Future of Life Institute (artificialintelligenceact.eu), "Article 6: Classification Rules for High-Risk AI Systems" (EU AI Act 조문, 개정 반영본), 2024/2026. https://artificialintelligenceact.eu/article/6/
- [R9] European Parliament and Council, "Regulation amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 ... (Digital Omnibus on AI)", PE-CONS 30/1/26 REV 1, 2026 (Regulation (EU) 2026/1744 최종 문안). https://data.consilium.europa.eu/doc/document/PE-30-2026-REV-1/en/pdf
- [R10] EFTA, "EEA-Lex: Regulation (EU) 2026/1744" (관보 게재 정보), 2026. https://www.efta.int/eea-lex/32026r1744
- [R11] Future of Life Institute (artificialintelligenceact.eu), "Annex I: List of Union Harmonisation Legislation" (개정 반영본), 2026. https://artificialintelligenceact.eu/annex/1/
- [R12] Future of Life Institute (artificialintelligenceact.eu), "Article 113: Entry into Force and Application" (개정 반영본), 2026. https://artificialintelligenceact.eu/article/113/
- [R13] Future of Life Institute (artificialintelligenceact.eu), "Article 14: Human Oversight", 2024/2026. https://artificialintelligenceact.eu/article/14/
- [R14] Future of Life Institute (artificialintelligenceact.eu), "Article 15: Accuracy, Robustness and Cybersecurity", 2024/2026. https://artificialintelligenceact.eu/article/15/
- [R15] NVIDIA, "Isaac Sim" (개발자 페이지), 2026. https://developer.nvidia.com/isaac/sim
- [R16] NVIDIA Blog, "NVIDIA Unveils 'Mega' Omniverse Blueprint for Building Industrial Robot Fleet Digital Twins", 2025-01-06. https://blogs.nvidia.com/blog/mega-omniverse-blueprint/
- [R17] NVIDIA Blog, "Into the Omniverse: How Digital Twins Are Scaling Industrial AI", 2025-04-16. https://blogs.nvidia.com/blog/how-digital-twins-scale-industrial-ai/
- [R18] ISO, "ISO/IEC 42001:2023 Information technology — Artificial intelligence — Management system", 2023. https://www.iso.org/standard/42001

EU AI Act 조문은 EUR-Lex 원문 페이지가 자동 조회로 열리지 않아, 개정 반영 조문은 artificialintelligenceact.eu에서, 개정 내용은 EU 이사회가 공개한 최종 문안(PE-CONS)에서 확인했습니다. EUR-Lex 통합본(https://eur-lex.europa.eu/eli/reg/2024/1689)과는 대조하지 않았습니다.
