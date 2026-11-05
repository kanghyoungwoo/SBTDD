| `python -m harness --root PROJECT doctor` | 로컬 CLI·로그인·프로젝트 사전 점검 |
| `python -m harness --root PROJECT check` | 계약 형식·참조·입력 경로 검증 |
| `python -m harness --root PROJECT run` | 전체 검사 실행·증거 저장 |
| `python -m harness --root PROJECT run --requirement ID` | 요구사항 하나에 연결된 검사 실행 |
| `python -m harness --root PROJECT status` | 현재 입력과 저장된 검사 결과 비교 |
| `python -m harness --root PROJECT init --brief FILE` | 빈 프로젝트의 명세·테스트 뼈대 생성 |
| `python -m harness --root PROJECT agent --requirement ID` | 요구사항 하나의 구현·검증·검토 |

## 결과 읽기

CLI는 JSON 객체를 출력합니다. 검사 프로그램의 출력은 결과의 `stdout`, `stderr`에 들어갑니다.

| 상태 | 의미 | 종료 코드 |
| --- | --- | --- |
| `valid` | 계약 구조와 입력 경로가 유효함 | 0 |
| `ready` | `init`의 구현 준비 완료 또는 `doctor`의 사전 점검 통과 | 0 |
| `passed` | 대상 검사 또는 개발 작업의 완료 조건 충족 | 0 |
| `failed` | 검사 실패 또는 구현·검토 시도 종료 | 1 |
| `stale` | 입력이 바뀌어 기존 검증 결과를 재사용할 수 없음 | 1 |
| `unverified` | 실행 기록이 없는 검사가 있음 | 1 |
| `needs_input` | 질문·환경 문제·범위 위반 등으로 확인이 필요함 | 1 |
| `error` | 계약·기록·파일 접근·AI 호출 등의 오류 | 2 |

`agent` 결과에서는 다음 세 필드를 함께 확인합니다.

- `status`: 선택한 개발 작업의 결과
- `project_status`: 전체 프로젝트의 최근 검사 상태
- `review_status`: Claude의 `approved`, `changes_requested`, `needs_input`, 아직 검토하지 않은 `unverified`, Codex 단독 흐름의 `not_requested`

이전에 실패했던 다른 요구사항이 남아 있어도 선택한 작업은 완료할 수 있습니다. `status` 명령은 저장된 테스트 결과를 조회하며 Claude의 검토 승인까지 합산하지 않습니다. 승인은 해당 `agent` 기록의 `review_fingerprint`와 일치하는 파일 상태에 적용됩니다.

## 실행 증거와 변경 감지

프로젝트별 `.harness/`에 증거를 보존합니다.

```text
.harness/
├── runs/                         # 검증 실행별 JSON 기록
├── init-runs/<session-id>/        # 초기화 기록·초안·AI 호출 자료
├── agent-runs/<session-id>/       # 개발 실행 기록
│   ├── run.json
│   ├── design/
│   ├── tests/
│   ├── implement-1/
│   └── review-1/                  # 검토 응답·changes.diff
├── incidents/                    # 증거 변경 감지 시 보존한 호출 자료
└── integrity-violation.json       # 증거 변경 감지 시 생성되는 표시
```

AI 호출 자료에는 프롬프트, 응답 스키마, 응답 JSON, 표준 출력·오류 로그가 포함됩니다. 응답 형식을 보정했다면 단계 폴더의 `repair/`에 보정 자료도 저장합니다.

두 종류의 변경 확인을 구분합니다.

- **검증 결과의 유효성:** 계약과 `inputs`의 경로·내용을 해시합니다. 입력이 바뀌면 기존 결과 전체를 보수적으로 `stale`로 처리합니다. 입력에는 테스트 설정·의존성 잠금 파일 등 결과에 영향을 주는 파일도 포함해야 합니다.
- **AI 수정 범위:** 호출 전후에 추적 입력 밖의 파일도 비교합니다. 증거 폴더는 별도로 검사하며, 기존 증거 변경이 감지되면 이력을 신뢰하지 않도록 표시하고 중단합니다.

검증 입력을 순회할 때는 `.git`, `.harness`, `.venv`, `__pycache__`, `.pytest_cache`를 제외합니다. AI 수정 범위를 검사하는 전체 프로젝트 비교는 이 검증 입력 해시와 별개입니다.

변경 감지는 호출 전후 비교이며 OS 보안 격리나 암호학적 증거 인증을 제공하지 않습니다. 실행 도중 변경 후 복원된 내용을 모두 탐지하지는 못합니다. 검사 명령은 프로젝트 코드를 실행하므로 신뢰할 수 있는 프로젝트에서 사용합니다.

## 중단 원인과 대응

`reason`, `message`, `question`과 연결된 기록을 먼저 확인합니다.

| `reason` | 확인할 내용 |
| --- | --- |
| `agent_question` | 질문에 답하고 명세의 모호한 부분 정리 |
| `red_not_observed`, `scaffold_not_red` | 기대·관측 Red ID, `check_diagnostics`, `verification_record` 확인 |
| `scope_changed`, `contract_changed` | `changed_files`와 실제 diff 검토 |
| `evidence_changed` | 무결성 표시·변경된 증거·incident 로그 확인 및 손상 기록 복구·격리 |
| `verification_setup` | 검사 도구·의존성·실행 오류·시간 초과 해결 |
| `invalid_response` | 원본 응답과 `repair/` 확인 |
| `agent_exit`, `agent_timeout`, `verification_error` | 호출 로그·검증 기록과 필요 시 `doctor` 확인 |
| `interrupted` | 저장된 단계와 현재 변경을 검토한 뒤 새 실행 시작 |
| `no_progress`, `attempt_limit`, `review_rejected` | 남은 실패 검사 또는 검토 지적 해결 |

잘못된 구조화 응답은 원래 작업을 반복하지 않는 읽기 전용 형식 보정을 한 번 시도합니다. 인증 오류·실행 실패·시간 초과는 같은 방식으로 자동 재호출하지 않습니다.

SIGINT·처리 가능한 SIGTERM 또는 시간 초과 시 자식 프로세스 트리 정리를 시도합니다. `agent`, `init`, 검사 실행은 처리 가능한 중단을 기록합니다. SIGKILL이나 Windows의 강제 프로세스 종료처럼 처리할 수 없는 종료에서는 기록을 보장할 수 없습니다.

중단 시 소스를 자동으로 되돌리지 않습니다. 세션 재개 기능은 없으며 다시 실행하면 현재 파일을 새로 검증합니다. 증거 변경이 감지됐다면 영향받은 기록을 검토·복구 또는 격리한 뒤 무결성 표시를 제거하고 재검증해야 합니다.

## Claude Code 스킬

[harness-workflow 스킬](.claude/skills/harness-workflow/SKILL.md)은 brief 작성, CLI 실행, 결과와 중단 원인 해석을 안내합니다. 이 저장소를 연 Claude Code 세션에서 다음과 같이 사용할 수 있습니다.

```text
/harness-workflow
```

새 프로젝트의 `init` 대상은 비어 있어야 하므로 스킬 파일은 Harness 저장소에 둡니다.

## 데모와 개발 검증

실제 모델을 사용하는 데모는 별도 복사본을 만들며 원본 예제를 보존합니다.

```powershell
# 자연어 요구사항 → 새 프로젝트 → 구현 → 검토
python -B examples/run_init_demo.py

# 재고 예제에 버그 주입 → 설계 → 수정 → 검증 → 검토
python -B examples/run_agent_demo.py
```

결과 프로젝트는 `.harness/demos/` 아래에 생성됩니다. 두 데모 모두 실제 AI 사용량을 소모합니다.

기본 테스트는 AI 응답을 대체하며 외부 모델을 호출하지 않습니다.

```powershell
python -B -m unittest discover -s tests -v
python -B -m harness check
python -B -m harness run
python -B -m harness status
```

테스트 모음은 CLI, AI 실행기, 역할 분리, 초기화, 변경 감지·증거 보호를 다룹니다. 하네스 자체의 요구사항과 검사 연결은 [harness.json](harness.json), 상세 설계는 [SPEC.md](SPEC.md)를 참고하세요.

## 현재 범위

자연어 초기화는 Python 3.11 이상·표준 라이브러리·unittest 프로젝트를 대상으로 합니다. 기존 프로젝트의 검증은 등록된 명령을 실행하며 필요한 도구와 의존성은 사용자가 준비합니다.

한 번의 AI 개발 실행은 요구사항 하나를 처리합니다. 같은 프로젝트의 동시 실행 조율·병렬 개발·세션 재개는 지원하지 않습니다. 명세 근거의 구조화된 표시와 별도 독립 QA 단계도 향후 검토 대상입니다.

테스트 통과와 Claude 승인은 검증 근거입니다. 생성된 명세의 업무적 가정과 테스트가 실제 사용자 의도를 충분히 반영하는지는 사람이 함께 확인해야 합니다.
