"""Local preflight only: never start a model call or perform login."""

import json
import os
import shutil
import subprocess
import sys

from .agent import CLAUDE_WRITER_MINIMUM, parse_version
from .core import fingerprint, load_manifest
from .guard import check_integrity


def run_doctor(root, provider='all'):
    checks = []

    def add(name, passed, reason, action='', **details):
        checks.append({'id': name, 'status': 'passed' if passed else 'failed',
                       'reason': reason, 'action': '' if passed else action, **details})

    add('python', sys.version_info >= (3, 11), 'version', 'Use Python 3.11 or newer.',
        version='.'.join(map(str, sys.version_info[:3])), executable=sys.executable)
    parent = root if root.exists() else next(p for p in root.parents if p.exists())
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
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
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
