"""Local preflight only: never start a model call or perform login."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .agent import CLAUDE_WRITER_MINIMUM, parse_version
from .core import JSON, fingerprint, load_manifest
from .guard import check_integrity
from .processes import NO_WINDOW
from .runtime import environment_inside, project_environment, same_path


VERSION_SCRIPT = "import sys; print('.'.join(map(str, sys.version_info[:3])))"


def run_doctor(root: Path, provider: str = 'all', python: str | None = None) -> JSON:
    root = root.resolve()
    checks: list[JSON] = []

    def add(name: str, passed: bool, reason: str, action: str = '', **details: Any) -> None:
        checks.append({'id': name, 'status': 'passed' if passed else 'failed',
                       'reason': reason, 'action': '' if passed else action, **details})

    add('python', sys.version_info >= (3, 11), 'version', 'Use Python 3.11 or newer.',
        version='.'.join(map(str, sys.version_info[:3])), executable=sys.executable)
    parent = root if root.exists() else next(p for p in root.parents if p.exists())
    inside = environment_inside(root)
    # Site hooks (.pth, sitecustomize) of the harness's own environment run inside the harness.
    add('isolation', inside is None, 'separate_environment' if inside is None else 'inside_project',
        'Run the harness from its own environment (pipx, uv tool or harness.pyz) and pass the '
        'project interpreter with --python.', environment=str(inside or sys.prefix))
    venv = project_environment(root) if root.is_dir() else None
    if python is not None:
        try:
            process = subprocess.run(
                [python, '-I', '-c', VERSION_SCRIPT], cwd=parent, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=15,
                creationflags=NO_WINDOW,
            )
            add('project.python', process.returncode == 0, 'version', f'Check that {python} runs.',
                executable=python, source='--python', version=process.stdout.strip()[:50])
        except subprocess.TimeoutExpired:
            add('project.python', False, 'timeout', f'Check {python} locally; timed out after 15 seconds.',
                executable=python)
        except OSError:
            add('project.python', False, 'launch_error', f'Check permissions of {python}.', executable=python)
    elif venv is not None and not same_path(venv, sys.executable):
        add('project.python', False, 'project_venv_not_selected',
            f'Checks would run on {sys.executable}; pass --python {venv} to use the project environment.',
            executable=sys.executable, project_venv=venv)
    else:
        add('project.python', True, 'harness_interpreter', executable=sys.executable,
            source='harness', version='.'.join(map(str, sys.version_info[:3])))
    add('workspace', parent.is_dir() and os.access(parent, os.R_OK | os.W_OK), 'access',
        'Use an accessible project directory.', path=str(root))
    try:
        check_integrity(root)
        add('evidence', True, 'integrity')
    except (ValueError, OSError) as error:
        add('evidence', False, 'integrity', str(error))
    workflow = None
    if (root / 'harness.json').exists():
        try:
            manifest = load_manifest(root)
            workflow = manifest.get('agent', {}).get('workflow')
            current = fingerprint(root, manifest)
            add('contract', True, 'valid', fingerprint=current)
        except (ValueError, OSError) as error:
            add('contract', False, 'invalid_contract', str(error))

    for name in ('codex', 'claude') if provider == 'all' else (provider,):
        executable = shutil.which(name)
        login = 'codex login' if name == 'codex' else 'claude auth login'
        if executable is None:
            add(name + '.cli', False, 'missing_cli', f'Install {name}, add it to PATH, then run {login}.')
            continue
        for stage, args in [('version', ['--version']),
                            ('auth', ['login', 'status'] if name == 'codex' else ['auth', 'status', '--json'])]:
            try:
                process = subprocess.run(
                    [executable, *args], cwd=parent, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=15,
                    creationflags=NO_WINDOW,
                )
                if stage == 'version':
                    add(name + '.cli', process.returncode == 0, 'version', f'Check the {name} installation.',
                        executable=executable, version=process.stdout.strip()[:200])
                    version = parse_version(process.stdout) if process.returncode == 0 else None
                    if name == 'claude' and workflow == 'claude' and version is not None:
                        needed = '.'.join(map(str, CLAUDE_WRITER_MINIMUM))
                        recent = version >= CLAUDE_WRITER_MINIMUM
                        add('claude.writer', recent, 'writer_supported' if recent else 'version_too_old',
                            f'The claude workflow needs Claude Code {needed} or newer; update Claude Code.',
                            minimum=needed)
                else:
                    logged_in = process.returncode == 0
                    if name == 'claude' and logged_in:
                        try:
                            data = json.loads(process.stdout)
                            logged_in = isinstance(data, dict) and data.get('loggedIn') is True
                        except json.JSONDecodeError:
                            add(name + '.auth', False, 'invalid_auth_status', f'Run {name} auth status locally.')
                            continue
                    # Never emit raw authentication output: it can contain account information.
                    add(name + '.auth', logged_in, 'authenticated' if logged_in else 'not_authenticated',
                        '' if logged_in else f'Run {login}, then rerun doctor.')
            except subprocess.TimeoutExpired:
                add(name + '.' + stage, False, 'timeout', f'Check {name} {" ".join(args)} locally; timed out after 15 seconds.')
            except OSError:
                add(name + '.' + stage, False, 'launch_error', f'Check permissions and the {name} installation.')

    return {'schema_version': 1, 'command': 'doctor', 'project_root': str(root),
            'status': 'ready' if all(c['status'] == 'passed' for c in checks) else 'needs_input',
            'checks': checks,
            'scope': 'Local CLI, login status and project checks only; no model request or quota check.'}
