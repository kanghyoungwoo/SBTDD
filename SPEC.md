# SDD · BDD · TDD Harness 명세 v0.4

## 목적과 범위

요구사항(SDD), 비즈니스 시나리오(BDD), 테스트 실행 결과를 연결한다.
개발자와 AI 실행기는 같은 CLI와 JSON 결과를 사용한다.
이번 버전은 로컬 단일 실행과 Claude 설계·검토, Codex 구현을 통한 요구사항 하나의 개발 루프를 대상으로 한다.

Python 3.11 이상과 표준 라이브러리로 구현한다. 프로젝트별 계약은
`harness.json`에 저장한다. 기존 명세를 기준으로 Claude가 구현 계획과 결과를 검토한다.
요구사항 결정은 사용자에게 있으며, CLI는 구조와 명시적으로 등록한 검사 결과를 검증한다.
빈 Python 프로젝트는 자연어 요구사항에서 명세·BDD와 API·테스트 뼈대를 생성해 같은 개발 루프에 연결한다.

## 계층별 계약

- SDD: `requirements`에 고유 ID와 요구사항 설명을 기록한다.
- BDD: `scenarios`에 고유 ID, 연결된 요구사항 ID 하나, Given/When/Then을 기록한다.
- 테스트: `checks`에 고유 ID, `acceptance` 또는 `unit` 종류, 시나리오 ID 목록,
  실행 명령을 기록한다. 여러 시나리오에서 하나의 검사를 공유할 수 있다.
- 모든 요구사항은 시나리오를 가져야 하며, 모든 시나리오는 적어도 하나의
  acceptance 검사를 가져야 한다. unit 검사만으로 BDD 검증을 대체하지 않는다.
- unit 검사는 필요할 때 추가한다. TDD는 개발 과정이며, unit 검사 통과만으로
  TDD를 수행했다고 판정하지 않는다.

Given/When/Then의 원본은 JSON이다. 별도 Gherkin 사본이나 파서를 두지 않는다.
요구사항이 모호하거나 기대 결과를 바꾸어야 하면 계약을 먼저 검토한다.

## 요구사항

| ID | 계약 |
| --- | --- |
| REQ-LINK | ID 중복, 존재하지 않는 참조, 시나리오 또는 acceptance 검사 누락, 잘못된 필드를 거부한다. |
| REQ-RUN | 등록된 명령을 프로젝트 루트에서 실행하고 종료 코드, 표준 출력·오류, 소요 시간을 기록한다. |
| REQ-STATE | 현재 입력에 대한 passed/failed/stale/unverified 상태를 검사·시나리오·요구사항별로 계산한다. |
| REQ-EVIDENCE | 실행별 증거를 저장하며, 선택 실행과 실행 중 입력 변경을 처리한다. |
| REQ-AGENT | 요구사항 하나를 선택해 테스트·구현·회귀 검증을 수행하고, 제한된 재시도와 중단 이유를 기록한다. |
| REQ-ROLES | Claude 설계 → Codex 구현 → CLI 검증 → Claude 검토를 연결하고, 검사와 검토가 모두 통과해야 완료한다. |
| REQ-INIT | 빈 프로젝트의 자연어 요구를 명세·BDD·미구현 API·실패 테스트로 변환하고 기존 개발 루프에 연결한다. |

## CLI 계약

```text
python -m harness [--root PROJECT] check
python -m harness [--root PROJECT] run [--requirement ID]
python -m harness [--root PROJECT] status
```

각 명령은 표준 출력으로 JSON 객체 하나를 출력한다. 스키마 버전은 1이다.

- `check`: 전체 계약의 구조와 입력 경로를 검증한다. 테스트를 실행하지 않는다.
- `run`: 모든 검사 또는 선택한 요구사항에 연결된 검사를 등록 순서로 실행한다.
  앞선 검사 실패 후에도 나머지 선택 검사를 실행한다. 결과는
  `.harness/runs/<run-id>.json`에 실행별로 보존한다.
- `status`: 테스트를 실행하지 않고 각 검사의 가장 최근 실행을 현재 입력과 비교한다.
- 종료 코드: 0 = 구조 검사 성공 또는 대상 검사 전체 통과,
  1 = 실패·미검증·오래된 결과 존재, 2 = 계약·기록·입출력 오류.

명령은 문자열 배열이며 셸 문법을 해석하지 않는다. `{python}` 토큰은 현재
Python 실행 파일로 치환한다. 검사별 `timeout_seconds`는 양의 정수이고 기본 30초다.
종료 코드 0은 passed, 그 외 종료 코드·실행 실패·시간 초과는 failed다.
명령과 그 하위 프로그램은 사용자 코드이므로 신뢰할 수 있는 프로젝트에서 실행한다.

## 검증 이력과 변경

`inputs`는 프로젝트 루트 기준 파일 또는 디렉터리 목록이다. 경로는 존재해야 하며
프로젝트 밖을 가리키거나 심볼릭 링크를 포함할 수 없다. JSON 계약 자체는 항상
입력에 포함된다. 디렉터리는 재귀적으로 읽되 `.git`, `.harness`, `.venv`,
`__pycache__`, `.pytest_cache`를 제외한다.

전체 입력의 상대 경로와 파일 내용을 SHA-256으로 요약한다. 등록된 디렉터리 안의
추가·수정·삭제가 요약에 반영된다. 입력 하나라도 달라지면 모든 기존 결과를 보수적으로
stale로 취급한다. `inputs` 밖의 파일, OS·환경변수·외부 서비스 변화는 추적하지 않는다.
따라서 의존성 잠금 파일 등 결과에 영향을 주는 파일도 inputs에 포함해야 한다.

실행 시작과 종료의 요약이 다르거나 종료 시 입력을 읽을 수 없으면 실행을 stale로
기록한다. 시작·종료 비교 사이에서 변경 후 복원된 입력까지 감지하지는 않는다.
이력은 로컬 개발 증거이며 변조 방지를 제공하지 않는다.

검사 상태는 다음 규칙으로 계산한다.

1. 실행 기록이 없으면 unverified.
2. 기록의 입력이 현재와 다르거나 실행 중 입력이 바뀌었으면 stale.
3. 그렇지 않으면 가장 최근 실행의 passed 또는 failed.

시나리오와 요구사항은 연결된 모든 검사의 상태를 집계한다.
집계 우선순위는 failed → stale → unverified → passed이며 상세 결과도 함께 제공한다.
선택 실행은 선택하지 않은 검사의 기존 결과를 덮어쓰지 않는다.

## 신규 프로젝트 초기화 계약

```text
python -m harness --root PROJECT init --brief FILE [--timeout-seconds 300]
```

FILE은 현재 작업 디렉터리 기준 UTF-8 자연어 요구 파일이다. PROJECT는 아직 없거나
원본 요구 파일과 `.harness` 이력을 제외하고 비어 있어야 한다. 기존 프로젝트의 계약을
덮어쓰거나 마이그레이션하지 않는다. 대상 폴더 안의 요구 파일은 생성물의 예약 이름과
충돌할 수 없다. Python >=3.11, 표준 라이브러리, unittest를 사용한다.

Claude의 spec 단계는 outcome/summary/question/title/design/requirements/scenarios를
반환한다. 명세·설계의 이름과 API 구조는 제안할 수 있지만 업무 규칙이 빠져 있으면
needs_input이다. 소스 코드는 생성하지 않는다. 요구사항·시나리오 연결은 기존 CLI의
계약 검증을 재사용한다. 시나리오마다 CHK-NNN과 tests/test_scenario_NNN.py를 대응시키고
고정된 unittest discover 명령을 하네스가 생성한다. 모델이 검사 명령을 지정하지 않는다.

초안은 `.harness/init-runs/<session-id>/draft/`에서 생성한다. BRIEF.md는 입력의 사본,
SPEC.md는 설계·요구사항·BDD의 문서, harness.json은 실행 가능한 계약이다. 추적 입력은
이 두 Markdown 파일과 src/, tests/이며 workflow는 claude-codex다.

Codex scaffold 단계는 src/와 tests/에 새 파일만 추가한다. 공개 API는 import 가능하고
미구현 동작은 src/에서 NotImplementedError를 발생시킨다. 테스트는 Given/When/Then의
실제 기대 결과를 단정하며 TODO 실패, skip, expectedFailure, 구현 자체의 mock을 쓰지 않는다.
초기 스캐폴드에서는 일반 unittest 테스트 메서드를 사용하고 subTest를 쓰지 않는다.

공통 CLI로 실제 검사를 실행한다. 각 시나리오에서 하나 이상의 테스트가 실행되고,
실행한 테스트 수와 오류 수가 같으며, 모든 오류는 src/의 NotImplementedError여야 한다.
unittest의 결과와 traceback에서 이를 확인한다. 선언된 red_check_ids도 전체 검사와
일치해야 한다. 빈 테스트, 이미 통과한 구현, import·문법 오류, 테스트 본문에서 직접
발생시킨 NotImplementedError는 준비 완료가 아니다. 업무 의미의 충족까지 자동 인증하지 않는다.

검사 중 입력이 바뀌거나 보호 파일이 바뀌면 중단한다. 원본 요구와 대상 폴더도 배치 직전에
다시 확인한다. 검증된 추적 파일만 기존 파일을 덮어쓰지 않고 복사하고, 입력 fingerprint가
동일한 Red 기록을 보존한다. 이후 agent가 실제 프로젝트 위치에서 기준 검사를 다시 실행한다.

ready(종료 코드 0)는 구현 준비 완료이며 테스트 상태는 failed다. needs_input은 1,
error는 2다. ready 응답에 생성 파일, 요구사항 ID, fingerprint, red_check_ids와 첫 대상의
next_command를 제공한다. init은 구현을 자동 시작하지 않으며 오류·질문·초안·로그는 보존한다.
새 호출은 새 초안을 만든다. agent는 기존과 같이 한 번에 요구사항 하나씩 처리한다.

## AI 실행기 계약

```text
python -m harness [--root PROJECT] agent [--requirement ID]
    [--max-attempts 3] [--timeout-seconds 300]
```

프로젝트는 `harness.json`에 선택적인 `agent` 설정을 추가한다.

```json
"agent": {"workflow": "claude-codex", "code_paths": ["src"], "test_paths": ["tests"]}
```

두 경로 목록은 비어 있을 수 없고, 서로 겹치지 않는 기존 파일·디렉터리여야 한다.
`inputs`에서 추적하는 범위 안에 있어야 하며 `harness.json`은 수정 범위에 포함할 수 없다.
기존 check/run/status는 agent 설정 없이 계속 사용할 수 있다.
선택 필드 workflow는 codex 또는 claude-codex다. 생략 시 codex로 기존 동작을 유지한다.

실행 순서는 다음과 같다.

1. 공통 CLI의 check, run, status를 호출해 전체 기준 결과를 새로 만든다.
2. 요구사항을 지정하지 않으면 명세 순서대로 첫 실패 요구사항을 선택한다.
   codex 흐름은 이미 통과한 대상을 AI 없이 종료한다. claude-codex 흐름에서 모두
   통과했으면 requirement_required로 대상 선택을 요청한다. 명시적으로 선택한 대상은
   Claude 설계·검토를 실행하며 승인 없이는 완료하지 않는다.
   Claude 설계는 기존 명세와 코드에서 구현 단계와 테스트 전략을 읽기 전용으로 생성한다.
3. 테스트 단계에서 Codex가 실패 이유를 검토하고 필요한 테스트를 추가한다.
   기존 테스트의 기대 결과 변경을 막기 위해 새 파일 추가만 허용한다.
   이미 충분한 실패 테스트가 있으면 그대로 사용한다.
4. 선택한 요구사항을 다시 실행한다. Codex가 지목한 검사에 일반적인 비영 종료 코드가
   관측되어야 구현 단계로 진행한다. 실행 실패·시간 초과는 Red 증거로 사용하지 않는다.
5. 구현 단계는 code_paths의 파일만 수정한다. 테스트와 나머지 추적 입력은 고정한다.
6. 구현 후 전체 검사를 실행한다. 선택한 요구사항이 통과하고, 기준 실행에서
   통과했던 검사에 회귀가 없으면 codex 흐름은 완료한다. claude-codex 흐름은 Claude가
   명세·설계·테스트·기준 실행 이후 diff·검사 기록을 검토하고 approved여야 완료한다.
7. 남은 실패, 회귀, 검토 수정 요청을 다음 Codex 시도에 전달한다. 구현 시도 상한은
   기본 3회이며 검토 재작업도 같은 한도를 사용한다. 변경 없는 재시도는 no_progress다.
   테스트 통과 상태에서 마지막 검토가 수정을 요청하면 review_rejected로 실패한다.

이미 통과한 대상을 선택했는데 최초 검토가 수정을 요청하면 테스트 단계로 이동하여
먼저 관측된 Red를 요구한다. 새 요구사항을 만들거나 기존 테스트를 완화하지 않는다.
설계 단계는 continue/needs_input, summary, question, steps, test_strategy를 반환한다.
검토 단계는 verdict(approved/changes_requested/needs_input), summary, question,
findings(path/issue/change)를 반환한다. 승인은 빈 findings, 수정 요청은 하나 이상의
구체적 finding이 필수다. 명세·테스트·허용 코드 경로 밖의 변경 요청은 needs_input이다.

자동 실행 한 번은 요구사항 하나만 처리한다. 기존에 실패한 다른 요구사항이 남아 있어도
선택한 요구사항은 완료할 수 있으며, 응답의 `project_status`로 전체 상태를 구분한다.
실행기에 재시작 시 세션을 이어가는 기능은 없다. 다시 실행하면 현재 파일에서 재검증한다.

## AI 실행기의 중단과 증거

| 결과 | 원인 |
| --- | --- |
| passed | 대상 요구사항 통과, 기존 통과 검사에 회귀 없음, Claude 흐름이면 검토 승인 |
| needs_input | 질문, 명세·허용 범위 위반, Red 부재, 실행 중 입력 변경, 검사 실행 환경 문제 |
| failed | 시도 한도 도달, 검토 수정 요청 미해결, 코드 변경 없는 반복 |
| error | AI 실행 실패·시간 초과·잘못된 응답, 검증 CLI 오류 |

종료 코드는 passed=0, needs_input/failed=1, error=2다.
중단 시 수정 내용을 자동으로 되돌리지 않고 이유와 변경 파일 목록을 기록한다.
허용 경로 검사는 inputs에 등록된 파일의 전후 비교다. 실행 중 변경 후 복원이나
inputs 밖의 파일까지 보장하는 보안 격리 수단이 아니며 Codex의 sandbox와 별개다.

`.harness/agent-runs/<session-id>/run.json`에 단계, 검증 실행 ID, 시도 횟수,
선택 요구사항, 전체 프로젝트 상태와 중단 이유를 저장한다. AI 호출마다 prompt,
JSON 응답, 표준 출력·오류를 같은 세션 폴더에 저장한다.
workflow, 단계별 provider, review_status를 기록하고 승인 시 review_fingerprint를 저장한다.
Claude 호출 전후의 추적 입력은 검증 기록의 fingerprint_after와 같아야 한다.
검토 중 입력 변경은 승인을 무효화한다. 설계·검토에서 추적 파일을 수정하면 중단한다.
검토에는 전체 검사 결과와 기준 실행 이후 변경 diff를 제공한다. 설계와 검토는 새 세션이다.
status 명령의 passed는 테스트 상태이며 AI 검토 승인을 포함하지 않는다. 검토 승인은
agent 실행의 run.json과 연결된 파일 상태에만 유효하며 변조 방지를 제공하지 않는다.

Codex 호출은 저장된 로그인과 모델 설정을 사용한다. workspace-write sandbox와
approval=never로 실행하므로 추가 권한이 필요한 작업은 실행기가 임의로 허용하지 않는다.
프로젝트가 Git 저장소가 아닌 예제도 지원하며, CLI가 요구하는 저장소 확인은 명시적으로
생략한다. AI 프로세스의 시간 초과 시 프로세스 트리 종료를 시도하고 자동 재시도하지 않는다.
Claude는 저장된 로그인을 사용하며 --safe-mode, 읽기 도구 Read/Glob/Grep만 제공,
dontAsk, --no-session-persistence로 호출한다. MCP 도구는 허용하지 않는다.
관리 정책은 유지되며 이 도구 제한과 추적 파일 비교가 OS 보안 격리를 대체하지 않는다.

Codex 응답은 `outcome`(continue/needs_input), `summary`, `question`, `red_check_ids`다.
질문은 needs_input일 때 필수이며, 테스트 단계의 continue는 실패 검사 ID를 포함해야 한다.
실제 실패를 assertion 오류로 해석하는 판단은 여전히 모델과 검토자의 책임이다.
실행기는 테스트 단계와 구현 단계를 분리하고 관측된 실패·통과를 기록한다.

## 검증 기준과 다음 단계

CLI를 외부 프로세스로 호출하는 인수 테스트로 정상·누락·실패·시간 초과·부분 실행·
변경 감지를 검증한다. 구현 전에 테스트 실패를 확인하고, 구현 후 통과를 확인한다.
하네스 자신의 `harness.json`도 같은 CLI로 검증한다.

실행기 테스트는 AI 응답을 대체하면서 실제 공통 CLI를 호출해 상태 전이를 확인한다.
Codex와 Claude 어댑터는 인자·표준 입력·구조화된 응답·오류 처리를 검증하고,
역할별 실행 순서, 거절 후 재검증, 질문·보호 파일·입력 변경 중단을 검증한다.
별도 재고 예제에서 실제 Claude 설계·검토와 Codex 구현 연결을 확인한다. 외부 모델을 사용하는 검사는 기본 테스트 실행에 포함하지 않는다.

기존 프로젝트의 명세 병합, 다른 언어의 초기 템플릿, 세션 재개, 변경 파일별 영향 분석은 v0.4 범위에 포함하지 않는다.
