from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .guard import changed_paths, check_integrity, mark_integrity_violation, plain_path, tree_snapshot
from .lock import environment, project_lock
from .processes import interrupt_on_term, run_command


EXCLUDED = {".git", ".harness", ".venv", "__pycache__", ".pytest_cache"}
STATES = ("failed", "stale", "unverified", "passed")


class HarnessError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise HarnessError(message)


def fields(value, required, optional, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(required <= value.keys(), f"{label}: missing fields {sorted(required - value.keys())}")
    require(value.keys() <= required | optional,
            f"{label}: unknown fields {sorted(value.keys() - required - optional)}")


def is_text(value):
    return isinstance(value, str) and bool(value.strip()) and "\0" not in value


def text_list(value, label):
    require(isinstance(value, list) and bool(value) and all(is_text(v) for v in value),
            f"{label} must be a nonempty array of nonempty strings")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise HarnessError(f"Invalid JSON in {path.name}: {error}") from error


def load_manifest(root):
    data = read_json(root / "harness.json")
    fields(data, {"version", "inputs", "requirements", "scenarios", "checks"}, {"agent"}, "harness.json")
    require(type(data["version"]) is int and data["version"] == 1, "version must be 1")
    text_list(data["inputs"], "inputs")
    definitions = {
        "requirements": ({"id", "description"}, set()),
        "scenarios": ({"id", "requirement", "given", "when", "then"}, set()),
        "checks": ({"id", "kind", "scenarios", "command"}, {"timeout_seconds"}),
    }
    indexes = {}
    all_ids = set()
    for name, (required, optional) in definitions.items():
        require(isinstance(data[name], list) and bool(data[name]), f"{name} must be a nonempty array")
        indexes[name] = {}
        for item in data[name]:
            fields(item, required, optional, name)
            for key in required - {"scenarios", "command"}:
                require(is_text(item[key]), f"{name}.{key} must be a nonempty string")
            require(item["id"] not in all_ids, f"duplicate ID: {item['id']}")
            all_ids.add(item["id"])
            indexes[name][item["id"]] = item
    for scenario in data["scenarios"]:
        require(scenario["requirement"] in indexes["requirements"],
                f"{scenario['id']}: unknown requirement {scenario['requirement']}")
    for check in data["checks"]:
        require(check["kind"] in {"acceptance", "unit"}, f"{check['id']}: invalid kind")
        text_list(check["scenarios"], f"{check['id']}.scenarios")
        text_list(check["command"], f"{check['id']}.command")
        timeout = check.get("timeout_seconds", 30)
        require(type(timeout) is int and timeout > 0, f"{check['id']}: timeout_seconds must be a positive integer")
        for scenario_id in check["scenarios"]:
            require(scenario_id in indexes["scenarios"], f"{check['id']}: unknown scenario {scenario_id}")
    for requirement in data["requirements"]:
        require(any(s["requirement"] == requirement["id"] for s in data["scenarios"]),
                f"{requirement['id']}: no scenarios")
    for scenario in data["scenarios"]:
        require(any(c["kind"] == "acceptance" and scenario["id"] in c["scenarios"] for c in data["checks"]),
                f"{scenario['id']}: no acceptance check")
    if "agent" in data:
        settings = data["agent"]
        fields(settings, {"code_paths", "test_paths"}, {"workflow"}, "agent")
        require(settings.get("workflow", "codex") in ("codex", "claude-codex"),
                "agent.workflow must be codex or claude-codex")
        inputs = [root / value for value in data["inputs"]]
        scopes = {}
        for name in ("code_paths", "test_paths"):
            text_list(settings[name], f"agent.{name}")
            scopes[name] = []
            for value in settings[name]:
                relative = Path(value)
                require(not relative.is_absolute() and not relative.drive and ".." not in relative.parts,
                        f"agent.{name}: expected a project-relative path: {value}")
                require(not EXCLUDED.intersection(relative.parts), f"agent.{name}: excluded path: {value}")
                path = root / relative
                require(path.exists() and not path.is_symlink() and path.resolve().is_relative_to(root),
                        f"agent.{name}: invalid path: {value}")
                require(any(path == entry or entry.is_dir() and path.is_relative_to(entry) for entry in inputs),
                        f"agent.{name}: path must be tracked by inputs: {value}")
                require(not (root / "harness.json").is_relative_to(path),
                        f"agent.{name}: harness.json must remain protected")
                scopes[name].append(path)
        require(not any(code.is_relative_to(test) or test.is_relative_to(code)
                        for code in scopes["code_paths"] for test in scopes["test_paths"]),
                "agent.code_paths and agent.test_paths must not overlap")
    return data


def input_files(root, manifest):
    files = {root / "harness.json"}

    def validate_path(path):
        require(not path.is_symlink(), f"Input symlinks are unsupported: {path}")
        require(path.resolve().is_relative_to(root), f"Input outside project: {path}")

    def walk_error(error):
        raise error

    for value in manifest["inputs"]:
        relative = Path(value)
        require(not relative.is_absolute() and not relative.drive and ".." not in relative.parts,
                f"Input must be a project-relative path: {value}")
        require(not EXCLUDED.intersection(relative.parts), f"Input uses an excluded directory: {value}")
        path = root
        for part in relative.parts:
            path = path / part
            validate_path(path)
        require(path.exists(), f"Input does not exist: {value}")
        if path.is_file():
            files.add(path)
        else:
            require(path.is_dir(), f"Input is not a file or directory: {value}")
            for directory, dirs, names in os.walk(path, onerror=walk_error):
                dirs[:] = sorted(name for name in dirs if name not in EXCLUDED)
                for name in dirs + names:
                    validate_path(Path(directory) / name)
                files.update(Path(directory) / name for name in names)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def fingerprint(root, manifest):
    # Always rehashed from content: the fingerprint is the long-lived validity basis of results.
    digest = hashlib.sha256()
    for path in input_files(root, manifest):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        with path.open("rb") as stream:
            digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def aggregate(states):
    return next(state for state in STATES if state in states)


def execute_check(root, check):
    command = [sys.executable if part == "{python}" else part for part in check["command"]]
    result = {"id": check["id"], "command": command, "status": "failed", "exit_code": None,
              "stdout": "", "stderr": "", "reason": "exit_code"}
    started = time.monotonic()
    try:
        process = run_command(
            command, cwd=root, text=True, encoding="utf-8", errors="replace",
            timeout=check.get("timeout_seconds", 30),
            env=environment(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"),
        )
        result.update(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr,
                      status="passed" if process.returncode == 0 else "failed")
    except subprocess.TimeoutExpired as error:
        def decode(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        result.update(reason="timeout", stdout=decode(error.stdout), stderr=decode(error.stderr))
    except OSError as error:
        result.update(reason="launch_error", stderr=str(error))
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result


@interrupt_on_term
def run_checks(root, manifest, before, requirement=None):
    if requirement is not None:
        require(any(r["id"] == requirement for r in manifest["requirements"]),
                f"Unknown requirement: {requirement}")
    with project_lock(root, "run"):
        return record_checks(root, manifest, before, requirement)


def record_checks(root, manifest, before, requirement):
    try:
        check_integrity(root)
    except ValueError as error:
        raise HarnessError(str(error)) from error
    scenario_ids = {s["id"] for s in manifest["scenarios"]
                    if requirement is None or s["requirement"] == requirement}
    checks = [c for c in manifest["checks"] if scenario_ids.intersection(c["scenarios"])]
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    evidence = root / ".harness"
    evidence_before = tree_snapshot(evidence)
    results = []
    interrupted = None
    for index, check in enumerate(checks):
        try:
            results.append(execute_check(root, check))
        except KeyboardInterrupt as error:
            interrupted = getattr(error, "signal_name", "SIGINT")
            for pending in checks[index:]:
                results.append({"id": pending["id"], "command": pending["command"], "status": "failed",
                                "exit_code": None, "stdout": "", "stderr": "Execution interrupted.",
                                "reason": "interrupted", "duration_seconds": 0})
            break
    evidence_changes = changed_paths(evidence_before, tree_snapshot(evidence))
    if evidence_changes:
        mark_integrity_violation(evidence, evidence_changes)
    snapshot_error = None
    try:
        after = fingerprint(root, manifest)
    except (HarnessError, OSError) as error:
        after = None
        snapshot_error = str(error)
    stable = before == after and not interrupted and not evidence_changes
    record = {
        "schema_version": 1, "command": "run", "run_id": run_id,
        "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": before, "fingerprint_after": after, "stable": stable,
        "status": aggregate([r["status"] for r in results]) if stable else "stale",
        "results": results,
    }
    if interrupted:
        record.update(status="needs_input", reason="interrupted", signal=interrupted)
    if evidence_changes:
        record.update(status="error", reason="evidence_changed", changed_files=evidence_changes,
                      error="Evidence changed during test execution; inspect .harness/integrity-violation.json.")
    if snapshot_error is not None:
        record["snapshot_error"] = snapshot_error
    directory = root / ".harness" / "runs"
    plain_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{run_id}.tmp"
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / f"{run_id}.json")
    return record


def read_record(path):
    record = read_json(path)
    require(isinstance(record, dict), f"Invalid run record: {path.name}")
    require(record.get("schema_version") == 1 and is_text(record.get("run_id"))
            and is_text(record.get("fingerprint")) and type(record.get("stable")) is bool
            and isinstance(record.get("results"), list) and bool(record["results"]),
            f"Invalid run record: {path.name}")
    seen = set()
    for result in record["results"]:
        require(isinstance(result, dict) and is_text(result.get("id"))
                and result.get("status") in ("passed", "failed"), f"Invalid result in record: {path.name}")
        require(result["id"] not in seen, f"Duplicate result in record: {path.name}")
        seen.add(result["id"])
    return record


def project_status(root, manifest, current):
    try:
        check_integrity(root)
    except ValueError as error:
        raise HarnessError(str(error)) from error
    latest = {}
    for path in sorted((root / ".harness" / "runs").glob("*.json")):
        record = read_record(path)
        for result in record["results"]:
            latest[result["id"]] = (record, result)
    return status_from_latest(manifest, current, latest)


def status_from_latest(manifest, current, latest):
    checks = []
    for check in manifest["checks"]:
        item = {"id": check["id"], "kind": check["kind"], "status": "unverified",
                "run_id": None, "last_result": None}
        if check["id"] in latest:
            record, result = latest[check["id"]]
            state = result["status"] if record["stable"] and record["fingerprint"] == current else "stale"
            item.update(status=state, run_id=record["run_id"], last_result=result["status"])
        checks.append(item)
    check_states = {c["id"]: c["status"] for c in checks}
    scenarios = []
    for scenario in manifest["scenarios"]:
        ids = [c["id"] for c in manifest["checks"] if scenario["id"] in c["scenarios"]]
        scenarios.append({"id": scenario["id"], "requirement": scenario["requirement"],
                          "checks": ids, "status": aggregate([check_states[key] for key in ids])})
    requirements = []
    for requirement in manifest["requirements"]:
        linked = [s for s in scenarios if s["requirement"] == requirement["id"]]
        requirements.append({"id": requirement["id"], "scenarios": [s["id"] for s in linked],
                             "status": aggregate([s["status"] for s in linked])})
    return {"schema_version": 1, "command": "status", "fingerprint": current,
            "status": aggregate(list(check_states.values())), "requirements": requirements,
            "scenarios": scenarios, "checks": checks}
