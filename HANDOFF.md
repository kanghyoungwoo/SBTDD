# 작업 인계 메모 (2026-11-05)

다른 컴퓨터에서 이어서 작업하기 위한 정리. 이 파일만 읽어도 다음 할 일을 시작할 수 있게 썼다.

## 1. 저장소와 브랜치

- 저장소: `kanghyoungwoo/SBTDD`
- 작업 브랜치: `claude/sharp-pasteur-u1adyq` (PR 없음, 모든 작업이 push되어 있음)

```bash
git clone https://github.com/kanghyoungwoo/SBTDD.git
```

```bash
cd SBTDD && git checkout claude/sharp-pasteur-u1adyq
```

## 2. 개발 환경

- Python 3.11 이상. 표준 라이브러리만 쓰므로 `pip install`이 필요 없다.
- 하네스의 `agent` 명령은 Claude Code CLI 2.1.248 이상이 필요하다. 로그인은 직접 한다.
- 개발 PC: ThinkPad(x86-64, Ubuntu). 실험·운영 PC: i7-7700 데스크톱(Linux). GPU는 빼고 RAM은 32GB를 권장한다.

설치가 제대로 됐는지 확인하는 명령. 2026-11-05 기준으로 아래 결과가 나왔다.

```bash
python3 -B -m unittest discover -s tests
```
→ 하네스 테스트 157개 통과(skip 1).

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" doctor
```

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" run
```
→ `passed`, 60/60 체크.

```bash
(cd projects/qqq-accumulator && python3 -B -m unittest discover -s tests)
```
→ QQQ 테스트 62개 통과.

## 3. 지금까지 한 일

### 3.1 Harness 개선 (저장소 루트 `harness/`)

- AgentWorkflow 아이디어(A1~A51) 가운데 "지금" 항목을 구현했다.
- 스냅샷 속도를 개선했다. stat 서명을 키로 쓰는 digest 캐시를 두고, 2초 안정 구간을 둔다.
- 오탐을 정리했다. 범위 밖이지만 무해한 변경(`.git`, 캐시, OS 메타데이터)은 `ignored_changes`로만 보고한다.
- Claude가 구현자로 일할 수 있게 했다(workflow `claude`). `--restricted`로 실행하며 경로를 제한한 Edit 규칙을 쓴다.
  `--review-model`과 `--implement-model`로 구현 모델과 리뷰 모델을 분리한다.
- OS 잠금(`harness/lock.py`)을 추가했다. 두 번째 실행은 `project_locked`로 거부한다.
- provider 사전 점검을 추가했다. 조건에 따라 `agent_missing`, `agent_outdated`를 낸다.
- 문서: `SPEC.md` v0.5, `README.md`, `.claude/skills/harness-workflow/SKILL.md`.
- 구현 언어는 Python을 그대로 쓰기로 했다(측정 근거는 이전 대화에서 다뤘다).

### 3.2 QQQ 장기 적립 프로그램 (`projects/qqq-accumulator/`)

brief의 구현 순서 가운데 1~2단계(백테스트와 기준선, 주문 상태 관리와 FakeBroker)를 끝냈다.

- 계약: `harness.json`에 요구사항 15개, 시나리오 60개, 체크 60개가 있다. workflow는 `claude`다.
- 요구사항 ID: CONFIG-001, DATA-001, STORE-001, BT-001~003, ORDER-001, RUN-001~005, NOTIFY-001,
  STATUS-001, TEST-001
- 코드: `src/app.py`(약 1,660줄), `src/models.py`. 테스트: `tests/test_scenario_001~060.py`, `tests/qqq_support.py`
- 하네스 agent로 요구사항을 하나씩 구현했다(구현 모델 sonnet, 리뷰 모델 opus, Claude 호출 약 60회, 약 1시간).
- 별도로 확인한 사항:
  - 코드에 float, 매도 함수, 네트워크 호출이 없다.
  - 표준 라이브러리만 쓴다.
  - SQLite는 WAL 모드와 STRICT 테이블이다.
  - 시간 판단은 zoneinfo America/New_York 기준이다.
- 가정: `SPEC.md` §10에 적었고 사용자가 수락했다.
- 동작 예시 1~15 가운데 네트워크가 필요 없는 항목은 FakeBroker와 FakeNotifier로 테스트가 있다.
- 현재 상태:
  - dry-run과 paper는 FakeBroker로만 동작한다.
  - live 단계는 거부한다(SCN-GRD-006).
  - 실제 증권사 어댑터는 아직 없다(SCN-GRD-007).

## 4. 확정된 결정

| 항목 | 결정 |
|---|---|
| 증권사 | 한국투자증권(KIS). QQQ 전용 계좌를 연다 |
| 사용 가능 현금 | 증권사 주문가능금액(현재 구현 그대로) |
| 배당·분할 | KIS 해외주식 기간별권리조회 API의 **확정** 값만 쓴다. 기존 멈춤 장치(분할 기록 없는 큰 가격 변화, 보유 수량 불일치)는 유지한다 |
| 거래일 달력 | CSV를 유지한다. KIS 결제일 API에는 조기 폐장 정보가 없다 |
| 운영 OS | Linux, systemd timer(15분마다 단발 실행). brief의 macOS/launchd는 4단계에서 바꾼다 |
| 3단계 분할 | 3a 모의투자 연결 → 모의 운영 확인 → 3b 실계좌 LOC |
| 프로그램 이름 후보 | Ballast(추천, 아직 확정하지 않음) |

KIS API 세부 내용(서버, TR ID, 필드, 미확인 항목)은 `projects/qqq-accumulator/docs/kis-api-notes.md`에 있다.

## 5. 앞으로 할 일 (순서대로)

### 5.1 사용자가 직접 할 일 (코딩 전에)

1. 한국투자증권에서 QQQ 전용 계좌를 열고 KIS Developers에서 API 키(모의, 실전)를 신청한다.
   - 키는 환경 변수로만 넣는다. 저장소나 채팅에 붙여 넣지 않는다.
   - AI 에이전트에게는 실전 키를 주지 않는다.
2. 고객센터에 해외주식 이벤트 수수료가 API 주문에도 적용되는지 확인한다.
3. 클라우드 세션을 쓸 경우 네트워크 Allowed domains에 다음을 추가한다.
   `securities.koreainvestment.com`, `apiportal.koreainvestment.com`, (필요하면) `openapi.koreainvestment.com`, `openapivts.koreainvestment.com`.
   추가하면 공식 문서를 직접 대조할 수 있다.
4. 텔레그램 봇을 만든다(BotFather). 토큰과 chat id는 4단계에서 환경 변수로 쓴다.
5. ThinkPad에 Ubuntu와 개발 환경을 설치하고, i7-7700 실험 PC를 준비한다.

### 5.2 3a단계: KIS 모의투자 연결 (다음 코딩 작업)

먼저 `docs/kis-api-notes.md`의 내용을 KIS Developers 공식 문서와 대조한다.
brief 규칙에 따라, 문서가 다르면 구현을 멈추고 질문한다. 그다음 요구사항과 시나리오를 `harness.json`에
추가하고 하네스 agent로 구현한다.

- 토큰 발급(`POST /oauth2/tokenP`). 프로젝트 폴더 밖의 사용자 전용 파일(권한 600)에 캐시한다.
- 인증 오류가 나면 재발급을 1회만 시도한다(동작 예시 14).
- 키와 토큰을 로그, DB, 알림에 남기지 않는다. 테스트로 검증한다.
- Broker 인터페이스 구현:
  - 매수 가능 금액(VTTS3007R)
  - 잔고(VTTS3012R)
  - 체결 내역(VTTS3035R)
  - 모의 주문(VTTT1002U, ORD_DVSN 00 지정가)
- 주문 POST는 재시도하지 않는다. 결과를 모르면 SENDING/UNKNOWN 흐름을 탄다.
- 일봉(HHDFS76240000, EXCD `NAS`)과 확정 권리(CTRGT011R)를 갱신한다.
- 실계좌 주문은 계속 막는다. 기본 테스트는 네트워크 없이 실행한다. HTTP 계층은 가짜 전송 객체로 테스트한다.

### 5.3 3b단계: 실계좌 LOC (모의 운영 확인 뒤)

- TTTT1002U, ORD_DVSN 34(LOC)를 쓴다.
- SCN-GRD-006(live 거부)과 SCN-GRD-007(어댑터 없음)은 계약과 테스트를 함께 고친다.
- 단계는 사용자가 설정 파일에서 직접 올린다. 첫 live 운영은 1회 한도와 월 한도를 소액으로 낮춰 LOC 체결을 확인한다.

### 5.4 4단계: 알림과 스케줄

- 텔레그램 Notifier:
  - 거래일마다 요약 1건을 보낸다. 주문이 없는 날도 보낸다.
  - 오류와 안전 장치 작동은 즉시 보낸다.
  - 알림이 실패해도 주문 상태는 바뀌지 않아야 한다.
- systemd service와 timer(15분 주기, 단발 프로세스), 운영 서버 설정. brief의 macOS/launchd 문구도 고친다.

### 5.5 이후 (별도 프로젝트)

- 자산 현황 웹: 읽기 전용, VPN 안에서만 접근, PWA. 목표 배분은 현금 30% / QQQ 50% / HFT 20%다.
- HFT: 거래소를 먼저 정한 뒤 Linux x86 실험 PC에서 C++로 진행한다. QQQ 프로그램과는 분리한다.

## 6. 아직 확인할 것 (KIS)

- 토큰 발급 횟수 제한(brief는 분당 1회라고 하지만 예제에서 확인하지 못함), 초당 호출 제한과 그 오류 코드
- 주문 응답 필드(주문번호 `odno` 등)
- 기간별권리조회 API의 모의 서버 지원 여부. 지원하지 않으면 모의 단계는 멈춤 장치에만 의존한다.
- 일봉 MODP 값의 정확한 의미
- API 주문 수수료와 이벤트 수수료 적용 여부

## 7. 지켜야 할 규칙 (brief에서)

- 프로그램과 AI 코딩 에이전트는 단계를 올리지 않고, 실계좌 키에 접근하지 않으며, 실계좌 주문을 실행하지 않는다.
- 키는 환경 변수로만 받는다. 키와 토큰은 로그, DB, 알림에 남기지 않는다.
- HALT 파일이 있으면 어느 단계에서든 주문을 보내지 않는다.
- 금액과 수량에 float를 쓰지 않는다(Decimal만 쓴다). 매도 함수를 만들지 않는다.
- 하네스 사용 시:
  - 테스트, 증거(`.harness/`), 명령을 고쳐서 통과시키지 않는다.
  - `.harness/lock`을 지우지 않는다.

## 8. 하네스로 다음 요구사항 구현하기

`harness.json`에 3a 요구사항을 추가한 뒤 실행한다.

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" check
```

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" agent --requirement REQ-ID --review-model opus --implement-model sonnet --timeout-seconds 1800
```

결과의 `status`, `reason`, `record`를 보고 다음 행동을 정한다(`.claude/skills/harness-workflow/SKILL.md`의 표 참고).
여러 요구사항을 이어서 돌리고 통과할 때마다 commit/push하려면, 이전 세션의 드라이버 스크립트처럼
요구사항마다 `agent`를 실행하고 `passed`가 아니면 멈추는 루프를 쓴다. 2시간 넘게 걸릴 수 있으니
`nohup`/`setsid`로 분리해서 실행한다.
