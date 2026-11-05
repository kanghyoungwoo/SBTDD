# SDD · BDD · TDD Harness 명세 v0.5

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
| REQ-GUARD | AI 호출과 검사 실행 전후로 프로젝트와 증거 폴더를 비교해 허용 범위 밖 변경을 거부하고, 증거가 바뀌면 이력을 신뢰하지 않도록 표시한다. |
| REQ-RECOVERY | 잘못된 AI 응답은 읽기 전용 형식 보정을 한 번만 시도하고, 중단 신호와 시간 초과에서는 자식 프로세스를 정리하고 중단을 기록한다. |
| REQ-PREFLIGHT | 모델을 호출하지 않고 로컬 CLI·로그인·프로젝트를 점검하며, 필요한 AI CLI가 없으면 검사와 모델 호출 전에 중단한다. |
| REQ-LOCK | 실행 기록을 쓰는 명령은 프로젝트마다 한 번에 하나만 실행하고, 기다리지 않고 거절된 명령은 증거를 바꾸지 않는다. |

## CLI 계약

```text
python -m harness [--root PROJECT] check
python -m harness [--root PROJECT] run [--requirement ID]
python -m harness [--root PROJECT] status
python -m harness [--root PROJECT] doctor [--provider all|codex|claude]
```

각 명령은 표준 출력으로 JSON 객체 하나를 출력한다. 스키마 버전은 1이다.

- `check`: 전체 계약의 구조와 입력 경로를 검증한다. 테스트를 실행하지 않는다.
- `run`: 모든 검사 또는 선택한 요구사항에 연결된 검사를 등록 순서로 실행한다.
  앞선 검사 실패 후에도 나머지 선택 검사를 실행한다. 결과는
  `.harness/runs/<run-id>.json`에 실행별로 보존한다.
- `status`: 테스트를 실행하지 않고 각 검사의 가장 최근 실행을 현재 입력과 비교한다.
- `doctor`: 모델을 호출하지 않는 사전 점검이다. 계약이 없어도 실행한다.
- 종료 코드: 0 = 구조 검사 성공, 대상 검사 전체 통과 또는 ready,
  1 = 실패·미검증·오래된 결과·확인 필요, 2 = 계약·기록·입출력·잠금 오류.

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

## 변경 감지와 증거 보호

fingerprint의 inputs 추적과 별도로, 실행기는 AI 호출마다 호출 전후의 프로젝트 전체를 비교한다.
비교 대상은 `.harness`를 제외한 모든 파일·디렉터리·링크이며 `.git`, `.venv`, 캐시 폴더도 포함한다.
다음 변경은 scope_changed(needs_input)로 중단한다.

- 현재 단계의 허용 경로 밖 변경. 설계·검토·응답 보정에는 허용 경로가 없다.
- 테스트 단계의 기존 파일 수정·삭제와 심볼릭 링크 생성.
- 허용 경로 안이라도 `.harness`, `.venv`, `__pycache__` 아래의 변경과 아래에 적은 `.git` 보호 파일의
  변경. 이 폴더들은 fingerprint와 검토 diff에 들어가지 않지만, Python은 `-B`에서도 캐시된
  bytecode를 읽으므로 실제로 실행되는 코드를 바꿀 수 있다.

IDE·파일 관리자·테스트 도구가 호출 중에 바꾸는 다음 파일은 실행되는 코드나 검증 대상을 바꾸지 못한다.
그래서 중단하지 않고 단계 기록의 `ignored_changes`(최대 20개)와 `ignored_change_count`로 보고하며,
구현 진행으로도 세지 않는다. 링크로 바뀐 경우는 예외 없이 위 규칙을 따른다.

- `.git` 안의 파일(index, refs, objects, FETCH_HEAD 등). 단 hooks, config, config.worktree,
  info/attributes는 git이 실행할 명령을 정하므로 하위 모듈·worktree의 같은 파일까지 계속 중단한다.
  `.git` 항목 자체(gitdir를 가리키는 파일 포함)를 바꾸는 것도 중단한다.
- 데이터 캐시 `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.hypothesis`와 `.coverage`, `.coverage.*`.
  검사 명령은 이 캐시에 따라 실행할 테스트가 달라지는 옵션(pytest의 `--lf`, `--ff`, `--sw` 등)을
  쓰지 않아야 한다.
- OS 메타데이터 `.DS_Store`, `Thumbs.db`, `desktop.ini`. 증거 폴더 비교에서도 이 세 이름은 무시한다.

새 폴더를 만드는 것은 그 안에 캐시만 있어도 일반 변경으로 판정한다.
허용 경로 밖의 변경은 이 검사가 막으므로 Claude 검토 diff는 추적 입력만 포함한다.

비교는 파일을 스트리밍으로 SHA-256 해시한다. 같은 프로세스 안에서는 크기와 수정 시각이 그대로이고
2초 이상 지난 파일의 해시를 재사용한다. POSIX에서는 ctime, inode, 장치 번호도 같아야 한다.
ctime은 사용자 프로세스가 되돌릴 수 없으므로 수정 시각을 되돌린 덮어쓰기도 감지한다. Windows에는
이에 해당하는 값이 없으므로, 내용을 바꾼 뒤 크기와 수정 시각까지 되돌린 파일은 놓칠 수 있다.
검증 결과의 근거인 fingerprint는 재사용 없이 매번 전체 내용을 해시하며, 값은 이전 버전과 같다.

`.harness` 증거 폴더는 AI 호출과 검사 실행 전후에 따로 비교한다. 기존 기록의 추가·수정·삭제가
감지되면 `.harness/integrity-violation.json`을 남기고 evidence_changed로 중단하며, 그 AI 호출의
자료는 `.harness/incidents/`에 보존한다. 이 표시가 있는 동안 run, status, agent, init은 이력을
사용하지 않고 오류로 끝난다. 사람이 영향받은 기록을 검토·복구 또는 격리한 뒤 표시를 지운다.
AI 호출의 프롬프트·스키마·로그·응답은 프로젝트 밖 임시 폴더에서 받아 Harness가 증거 폴더로 복사한다.

실행기가 호출하는 검증 CLI는 Harness 설치 위치에서 Python `-I` 격리 모드로 실행한다. 따라서
프로젝트의 `harness.py`, `sitecustomize.py`, PYTHONPATH가 검증기를 대체하지 못한다.
이 감지는 호출 전후 비교이며 OS 보안 격리나 암호학적 증거 인증이 아니다. 호출 중 변경 후
복원된 내용과, 호출이 끝난 뒤에도 남은 프로세스가 쓰는 내용은 보장하지 않는다.

## 동시 실행 잠금

run, agent, init은 증거를 쓰기 전에 `.harness/lock`에 운영체제 파일 잠금(POSIX `flock`,
Windows `msvcrt.locking`)을 건다. 잠금을 얻지 못한 명령은 기다리지 않고, 파일을 하나도 쓰지 않은 채
`reason: project_locked`와 `lock_owner`(명령·PID·시작 시각)를 포함한 error(종료 코드 2)로 끝난다.
잠금은 보유 프로세스가 강제 종료를 포함해 어떤 이유로든 끝나면 운영체제가 해제하므로 잠금 파일을
지울 필요가 없다. check, status, doctor는 증거를 쓰지 않으므로 잠그지 않는다.

agent와 init이 호출하는 검증 CLI는 보유자가 넘긴 일회용 토큰으로 같은 잠금 아래에서 실행된다.
`.harness/lock-owner.json`에는 토큰의 SHA-256만 기록한다. AI CLI와 검사 명령의 환경에서는 토큰을
제거하므로, 이들이 실행한 Harness 명령은 잠금을 빌리지 못하고 거절된다. 잠금은 정직한 프로세스
사이의 조율 수단이며 보안 경계가 아니다.

## 사전 점검

`doctor`는 Python 버전, 프로젝트 접근, 증거 무결성 표시, 존재하는 계약, Codex·Claude CLI의
경로·버전·로그인 상태를 확인한다. `--provider`로 한 CLI만 확인할 수 있다. 모델 호출, 로그인,
사용량 확인은 하지 않으며 인증 명령의 출력 원문을 결과에 넣지 않는다. 모든 항목이 통과하면 ready,
아니면 항목별 reason과 action을 포함한 needs_input이다.

agent와 init은 시작할 때 workflow에 필요한 CLI가 PATH에 있는지 먼저 확인한다. codex 흐름은 Codex,
claude-codex 흐름과 init은 Claude와 Codex가 필요하다. 하나라도 없으면 기준 검사와 모델 호출 전에
`agent_missing`과 `missing` 목록으로 끝난다.

## 신규 프로젝트 초기화 계약

```text
python -m harness --root PROJECT init --brief FILE [--timeout-seconds 300]
```

FILE은 현재 작업 디렉터리 기준 UTF-8 자연어 요구 파일이다. PROJECT는 아직 없거나
원본 요구 파일과 `.harness` 이력을 제외하고 비어 있어야 한다. 기존 프로젝트의 계약을
덮어쓰거나 마이그레이션하지 않는다. 대상 폴더 안의 요구 파일은 생성물의 예약 이름
(SPEC.md, harness.json, src, tests, .harness, .gitignore)과 충돌할 수 없다.
Python >=3.11, 표준 라이브러리, unittest를 사용한다.

Claude의 spec 단계는 outcome/summary/question/title/design/requirements/scenarios를
반환한다. 명세·설계의 이름과 API 구조는 제안할 수 있지만 업무 규칙이 빠져 있으면
needs_input이다. 브리프가 정하지 않은 내용은 질문하거나, 사용자가 검토할 수 있도록 설계에
가정으로 명시한다. 소스 코드는 생성하지 않는다. 요구사항·시나리오 연결은 기존 CLI의
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
scaffold_not_red는 조건을 충족하지 못한 검사마다 `stub_red_problems`에 사유를 남긴다.
사유는 no_tests, not_failing, import_error, assertion_failures, partial_errors,
unexpected_outcomes, not_source_stub, unrecognized_output 또는 timeout 같은 실행 사유다.

검사 중 입력이 바뀌거나 보호 파일이 바뀌면 중단한다. 원본 요구와 대상 폴더도 배치 직전에
다시 확인한다. 검증된 추적 파일만 기존 파일을 덮어쓰지 않고 복사하고, 입력 fingerprint가
동일한 Red 기록을 보존한다. `.harness/`, `__pycache__/`, `.venv/`를 제외하는 `.gitignore`도
만든다. `.gitignore`는 추적 입력이 아니므로 fingerprint를 바꾸지 않는다.
이후 agent가 실제 프로젝트 위치에서 기준 검사를 다시 실행한다.

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

1. 필요한 AI CLI를 확인한 뒤, 공통 CLI의 check, run, status를 호출해 전체 기준 결과를 새로 만든다.
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

검토자는 이번 라운드에서 발견한 막는 문제를 모두 나열한다. 선택한 요구사항의 시나리오가
실행하는 동작에 남은 스텁·플레이스홀더·TODO·NotImplementedError는 구현으로 인정하지 않는다.
다른 요구사항을 위한 스텁은 요구사항을 하나씩 개발하는 과정에서 정상이므로 지적하지 않는다.
모든 AI 역할은 확인하지 않은 내용을 결과로 주장하지 않는다. 이 규칙은 지시문으로 전달되며
모델의 준수 여부는 검사 결과와 사람의 확인으로 판단한다.

자동 실행 한 번은 요구사항 하나만 처리한다. 기존에 실패한 다른 요구사항이 남아 있어도
선택한 요구사항은 완료할 수 있으며, 응답의 `project_status`로 전체 상태를 구분한다.
실행기에 재시작 시 세션을 이어가는 기능은 없다. 다시 실행하면 현재 파일에서 재검증한다.

## AI 실행기의 중단과 증거

| 결과 | 원인 |
| --- | --- |
| passed | 대상 요구사항 통과, 기존 통과 검사에 회귀 없음, Claude 흐름이면 검토 승인 |
| needs_input | 질문, 명세·허용 범위 위반, 증거 변경, Red 부재, 실행 중 입력 변경, 검사 실행 환경 문제, 중단 신호 |
| failed | 시도 한도 도달, 검토 수정 요청 미해결, 코드 변경 없는 반복 |
| error | 필요한 AI CLI 없음, AI 실행 실패·시간 초과·잘못된 응답, 검증 CLI 오류, 다른 명령의 잠금 |

종료 코드는 passed=0, needs_input/failed=1, error=2다.
중단 시 수정 내용을 자동으로 되돌리지 않고 이유와 변경 파일 목록을 기록한다.
수정 범위와 증거의 변경 감지는 변경 감지와 증거 보호 절을 따른다. 이 감지는 Codex의 sandbox와
별개이며 그것을 대체하지 않는다.

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
생략한다. AI 프로세스의 시간 초과나 중단 시 프로세스 트리를 정리한다. POSIX는 프로세스 그룹에
SIGTERM을 보내고 3초 뒤 SIGKILL을 보내며, Windows는 `taskkill /T /F`로 바로 종료한다.
SIGINT와 처리 가능한 SIGTERM은 run, agent, init에서 interrupted로 기록한다. SIGKILL처럼
처리할 수 없는 종료는 기록을 보장하지 않으며 SIGHUP은 처리하지 않는다.

인증 오류·실행 실패·시간 초과는 다시 호출하지 않는다. 구조화 응답이 스키마나 검증 규칙에 맞지
않을 때만 원래 작업을 반복하지 않는 형식 보정을 한 번 호출한다. Codex 보정은 read-only sandbox,
Claude 보정은 도구 없이 실행하고 보정 중 프로젝트 변경은 scope_changed다. 보정 자료는 단계 폴더의
`repair/`에 저장하며, 보정 결과도 맞지 않으면 invalid_response로 끝난다.
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
변경 감지·증거 보호, 형식 보정·중단, 사전 점검은 `tests/test_hardening.py`, 잠금은
`tests/test_lock.py`가 검증한다. 저장소의 모든 테스트는 `harness.json`의 검사 하나 이상에
연결되어야 하며, 연결되지 않은 테스트가 있으면 REQ-LINK 검사가 실패한다.
별도 재고 예제에서 실제 Claude 설계·검토와 Codex 구현 연결을 확인한다. 외부 모델을 사용하는 검사는 기본 테스트 실행에 포함하지 않는다.

기존 프로젝트의 명세 병합, 다른 언어의 초기 템플릿, 세션 재개, 변경 파일별 영향 분석은 v0.5 범위에 포함하지 않는다.
SIGHUP 처리, Windows 프로세스의 단계적 종료, 잠금 대기도 이번 범위가 아니다.
