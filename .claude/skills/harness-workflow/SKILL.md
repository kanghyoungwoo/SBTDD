---
name: harness-workflow
description: Prepare a testable brief and operate this SDD/BDD/TDD Harness through init, agent, verification and failure diagnosis. Use for requests to start or develop a project with Harness, or explain a Harness run result.
---

Use the common Harness CLI as the source of execution evidence. This skill coordinates the
outer conversation; the harness itself invokes Claude for design/review and Codex for code.

## Establish the task

Identify the target project and whether the user wants planning, a new project, implementation,
or diagnosis of an existing run. Use existing authorization; do not repeatedly ask to execute
work the user already requested. A request for explanation alone does not authorize model runs.

Run commands from the Harness checkout containing `harness/__main__.py` (three directories
above this skill), with an absolute target path after `--root` and before the subcommand.
Read the relevant command section in [README.md](../../../README.md) when needed.

## New project

Write a UTF-8 brief from the user's stated requirements. Include concrete input/output examples,
error behavior or caller preconditions, and exclusions when known. Keep original language and
intent. Do not require a particular heading format or invent business rules to fill gaps.
Ask a focused question when an unresolved decision changes observable behavior. For example,
an ASCII output separator does not determine how non-ASCII input whitespace should behave.

The target must be empty or contain only the original brief and `.harness` history. Do not
put this skill or other setup files inside a new target before `init`.

```text
python -B -m harness --root PROJECT doctor
python -B -m harness --root PROJECT init --brief ABSOLUTE_BRIEF_PATH
```

Inspect `status`, `reason`, `question`, `record` and `draft`. `ready` means every declared check
reached an unimplemented source stub; it is not completed implementation. Read the generated
BRIEF.md, SPEC.md and scenario assertions for unconfirmed assumptions before starting `agent`.
If implementation was requested and the contract matches the user intent, continue with the
returned `next_command`. With multiple requirements, process the selected IDs sequentially.

## Existing project

```text
python -B -m harness --root PROJECT doctor
python -B -m harness --root PROJECT check
python -B -m harness --root PROJECT agent --requirement REQUIREMENT_ID
```

Use `doctor --provider codex` for a Codex-only workflow. Doctor is a local preflight; it does
not confirm remaining usage or perform a model request. Do not install tools, change models,
or log in on the user's behalf merely because doctor reports a problem.

For Claude design and review the manifest uses `agent.workflow = "claude-codex"`. Respect
`code_paths`, `test_paths` and the contract. Do not edit tests, evidence or commands to obtain
a pass. Harness refuses a second `run`, `agent` or `init` in the same project with
`project_locked`; wait for the first command and never delete `.harness/lock` to get past it.
Harness has no resume operation; a new invocation starts with fresh verification of the current files.

## Read results and choose the next action

| Result or reason | Response |
| --- | --- |
| `passed` | Report the selected requirement, `project_status`, `review_status` and record path. A target pass can coexist with pre-existing unrelated failures. |
| `agent_question` | Present the question with the specific conflicting requirement; apply the user's answer to the brief/contract only within their authorized scope. |
| `red_not_observed`, `scaffold_not_red` | Compare expected, declared and observed Red IDs, per-check `stub_red_problems`, `check_diagnostics` and `verification_record`. Do not manufacture failing tests. |
| `scope_changed`, `contract_changed` | Show `changed_files`; review the actual diff. Do not silently restore source or weaken the allowed scope. Phase `ignored_changes` only lists benign `.git`, cache and OS metadata edits that did not stop the run. |
| `evidence_changed` | Stop trusting history. Inspect `integrity_record`, changed evidence and preserved incident logs. Repair or quarantine affected records before removing the marker and rerunning checks. Never delete the marker just to continue. |
| `interrupted` | Inspect changes and saved phase status before a fresh run. No automatic rollback or session resume is implied. |
| `invalid_response` | One format-only repair has already been attempted. Inspect original logs and `repair/`; do not blindly repeat implementation. |
| `agent_missing` | Name the `missing` CLIs and the login command; nothing ran yet. Do not install or log in for the user. |
| `project_locked` | Another harness command owns the project (`lock_owner`). Wait or ask; do not delete lock files. |
| `agent_exit`, `agent_timeout`, `verification_setup` | Read phase logs or the verification record, then use doctor for local setup issues. Do not loop on authentication, usage limits or timeouts. |
| `no_progress`, `attempt_limit`, `review_rejected` | Explain remaining failed checks or actionable review findings; do not keep extending the attempt limit without addressing the cause. |

Exit codes are 0 for success/ready, 1 for incomplete work or needed input, and 2 for errors.
`status` reports historical test evidence, not a fresh independent QA verdict. Run checks again
after editing files; previous review approval applies only to its recorded fingerprint.
