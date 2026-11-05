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

- Python 3.11 이상. 하네스 실행에는 표준 라이브러리만 쓰므로 `pip install`이 필요 없다.
- 다른 폴더에서 하네스를 쓰려면 프로젝트와 분리된 환경에 설치한다: `pipx install .` 또는 `uv tool install .`,
  또는 `python3 -B tools/build_zipapp.py`로 만든 `dist/harness.pyz`. 프로젝트에 `.venv`가 있으면 `--python`으로
  그 인터프리터를 넘긴다(아래 3.1).
- 타입 검사(개발 전용): `uv run --only-group dev mypy` 또는 `python3 -m pip install mypy==2.3.1 && python3 -m mypy`.
- 하네스의 `agent` 명령은 Claude Code CLI 2.1.248 이상이 필요하다. 로그인은 직접 한다.
- 개발 PC: ThinkPad(x86-64, Ubuntu). 실험·운영 PC: i7-7700 데스크톱(Linux). GPU는 빼고 RAM은 32GB를 권장한다.

설치가 제대로 됐는지 확인하는 명령. 2026-11-05 기준으로 아래 결과가 나왔다.

```bash
python3 -B -m unittest discover -s tests
```
→ 하네스 테스트 167개 통과(skip 1).

```bash
python3 -B -m harness run
```
→ 하네스 자기 계약 13개 요구사항, 13개 체크 `passed`.

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" doctor
```

```bash
python3 -B -m harness --root "$PWD/projects/qqq-accumulator" run
```
→ `passed`, 66/66 체크.

```bash
(cd projects/qqq-accumulator && python3 -B -m unittest discover -s tests)
```
→ QQQ 테스트 72개 통과.

## 3. 지금까지 한 일

### 3.1 Harness 개선 (저장소 루트 `harness/`)

- AgentWorkflow 아이디어(A1~A51) 가운데 "지금" 항목을 구현했다.
- 스냅샷 속도를 개선했다. stat 서명을 키로 쓰는 digest 캐시를 두고, 2초 안정 구간을 둔다.
- 오탐을 정리했다. 범위 밖이지만 무해한 변경(`.git`, 캐시, OS 메타데이터)은 `ignored_changes`로만 보고한다.
- Claude가 구현자로 일할 수 있게 했다(workflow `claude`). `--restricted`로 실행하며 경로를 제한한 Edit 규칙을 쓴다.
  `--review-model`과 `--implement-model`로 구현 모델과 리뷰 모델을 분리한다.
- OS 잠금(`harness/lock.py`)을 추가했다. 두 번째 실행은 `project_locked`로 거부한다.
- provider 사전 점검을 추가했다. 조건에 따라 `agent_missing`, `agent_outdated`를 낸다.
- 문서: `SPEC.md` v0.6, `README.md`, `.claude/skills/harness-workflow/SKILL.md`.
- 구현 언어는 Python을 그대로 쓰기로 했다(측정 근거는 이전 대화에서 다뤘다). 백지에서 다시 비교해도
  Python이 근소하게 1위였고, 그때 짚은 약점 세 가지를 v0.6에서 보완했다.
  1. 실행 환경 분리(REQ-RUNTIME): `--python PYTHON`이 검사의 `{python}`만 프로젝트 인터프리터로 바꾼다.
     가상환경 심볼릭 링크는 풀지 않는다. agent·init이 쓰는 검증기는 `-I -S`로 실행해 `.pth`·sitecustomize가
     검증 결과를 위조하지 못한다(`-S`를 빼면 위조되는 것을 테스트로 확인). doctor에 `isolation`,
     `project.python` 항목을 추가했고, 실행 기록에 `interpreters`를 남긴다.
  2. 설치·배포(REQ-DIST): `uv tool install .` 설치를 Python 3.11 도구 환경에서 확인했다(pipx는 같은
     패키지 설치 방식이지만 이 세션에 없어 직접 실행하지 않았다). 표준 라이브러리로 만드는 재현 가능한 단일 파일
     `harness.pyz`(`tools/build_zipapp.py`)를 추가했다.
  3. 정적 타입: `harness/`와 `tools/` 전체에 타입 힌트를 달고 mypy `--strict`가 Linux·Windows·macOS
     분기에서 모두 통과한다(pyright도 0건). mypy가 없는 PC에서도 `run`이 통과하도록 `harness.json` 검사에는
     넣지 않고, GitHub Actions(`.github/workflows/ci.yml`)가 3개 OS × Python 3.11·3.13 테스트와 타입 검사를 돌린다.

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

### 3.3 매도 실험 규칙 ma_band (REQ-BT-004, 2026-11-05 추가)

사용자 질문 "비쌀 때 팔고 쌀 때 사면 더 모을 수 있지 않나?"를 숫자로 확인하려고 **백테스트 전용** 규칙을 넣었다.
운영 매도는 여전히 없다. Broker에 매도 메서드가 없고, `operating_rule`로 지정하면 `run`이 CONFIG_ERROR로 거부한다.
이 요구사항은 하네스 agent가 아니라 이 세션에서 직접 구현했다. 계약(`harness.json`, `SPEC.md`)과 테스트
061~066은 함께 추가했고, 하네스 `run`으로 66/66 체크 통과를 확인했다.

- 규칙: 분할 조정 N일 단순 이동평균(SMA)을 증분으로 계산한다.
  - 종가가 SMA×(1+sell_above_pct%) 이상이면 보유분의 sell_fraction_pct%를 판다. T+1 종가에 체결하며 지정가 여유가 적용된다.
  - 판 뒤에는 종가가 SMA×(1+rebuy_at_or_below_pct%) 이하가 될 때까지 현금으로 기다린다(입금도 사지 않음). 조건이 맞으면 전액 다시 산다.
- 비용 모형(가정, SPEC §6):
  - 매도 수수료를 반영한다.
  - 평균 원가 기준으로 양도차익을 계산한다.
  - 연간 기본공제 후 세율을 적용한다. 세금은 다음 해 첫 봉에 납부하며, 미납분은 재투자하지 않는다.
  - 달러 기준이며, 환차손익과 5월 신고 시점은 반영하지 않는다.
- 설정: rules에 ma_band가 있으면 다음 값이 필수다.

  ```toml
  [sell_sim]
  sell_fee_pct = 0.25            # 계좌의 실제 해외주식 수수료로 바꾼다
  capital_gains_tax_pct = 22     # 양도소득세 + 지방세
  annual_exemption_usd = 1800    # 연 250만 원 공제를 달러로 환산한 값
  ```
- 규칙 예시 파일: `projects/qqq-accumulator/docs/band-rules.example.json`(200일선 +20% 절반 매도 등 3개)
- 결과 JSON의 규칙별 지표에 `sell_count`, `realized_gain_usd`, `tax_usd`가 추가됐다.
- 테스트로 확인한 성질:
  - 매도 뒤 가격이 내려오면 주수가 늘어난다(1주 → 1.333333주).
  - 세금 22%가 붙으면 늘어나는 폭이 줄어든다(1.284444주).
  - 매도 뒤 가격이 계속 오르면 기준선보다 주수가 줄어든다(환산 0.8주 대 1주).
  - 분할로 가격이 반이 돼도 재매수 신호로 쓰지 않는다.
  - 공제는 해마다 따로 적용된다.
- **아직 실데이터로 돌려 보지 않았다.** 이 저장소에는 실제 QQQ 일봉 CSV가 없고, 이 세션 네트워크에서
  stooq·Yahoo가 막혀 있었다. 아래 5.2를 참고한다.

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

### 5.2 매도 실험 백테스트를 실데이터로 실행 (데이터만 있으면 바로 가능)

1. 실제 QQQ 데이터를 준비한다.
   - 일봉 CSV: `date,open,high,low,close,volume,split_factor,dividend`. 원시 가격으로 1999년 이후 전체를 쓴다.
     2000-03-20 2:1 분할과 배당 포함.
   - 같은 기간 거래일 달력 CSV: `date,is_open,close_time`.
   - KRW 입금으로 시험하려면 환율 CSV도 준비한다. 형식은 `projects/qqq-accumulator/SPEC.md` §3에 있다.
   - 출처 후보: KIS 일봉 API(3a 이후), 또는 직접 내려받은 CSV. 파일 해시가 결과 JSON에 기록된다.
2. 실제 입금 주기와 금액, 수수료, `sell_sim` 값, 채택 기준(holdout 기간, 롤링 창, 최소 초과율)을 설정 파일에 넣는다.
3. `projects/qqq-accumulator`에서 다음 명령을 실행한다(진입점은 `src/__main__.py`).

   ```bash
   python3 -B -m src --config CONFIG import-data --file calendar.csv
   ```

   ```bash
   python3 -B -m src --config CONFIG import-data --file bars.csv
   ```

   ```bash
   python3 -B -m src --config CONFIG backtest --rules docs/band-rules.example.json
   ```

4. 볼 것:
   - 평가 구간의 `final_shares_diff_vs_baseline`, `equivalent_shares_diff_vs_baseline`
   - 롤링 창에서 기준선 이상인 비율(`rolling`)
   - 세금(`tax_usd`)과 매도 횟수
5. 매개변수를 여러 번 바꿔 보면 평가 구간에 과적합된다. 매개변수는 조정 구간(tuning) 결과만 보고 정하고,
   평가 구간은 마지막에 한 번만 본다.
6. 채택 기준을 넘더라도 운영에 넣으려면 brief의 "매도 제외"를 사용자가 직접 바꿔야 한다.
   그 경우 실계좌 매도 주문, 세금 기록, 보유 수량 대조를 새 요구사항으로 설계한다. 지금은 계획에 없다.

### 5.3 3a단계: KIS 모의투자 연결 (다음 코딩 작업)

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

### 5.4 3b단계: 실계좌 LOC (모의 운영 확인 뒤)

- TTTT1002U, ORD_DVSN 34(LOC)를 쓴다.
- SCN-GRD-006(live 거부)과 SCN-GRD-007(어댑터 없음)은 계약과 테스트를 함께 고친다.
- 단계는 사용자가 설정 파일에서 직접 올린다. 첫 live 운영은 1회 한도와 월 한도를 소액으로 낮춰 LOC 체결을 확인한다.

### 5.5 4단계: 알림과 스케줄

- 텔레그램 Notifier:
  - 거래일마다 요약 1건을 보낸다. 주문이 없는 날도 보낸다.
  - 오류와 안전 장치 작동은 즉시 보낸다.
  - 알림이 실패해도 주문 상태는 바뀌지 않아야 한다.
- systemd service와 timer(15분 주기, 단발 프로세스), 운영 서버 설정. brief의 macOS/launchd 문구도 고친다.

### 5.6 이후 (별도 프로젝트)

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
