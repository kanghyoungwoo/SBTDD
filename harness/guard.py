"""Change detection; this is not an operating-system sandbox."""

import hashlib
import json
import os
from pathlib import Path
import stat


INTEGRITY_MARKER = 'integrity-violation.json'


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def plain_path(path):
    for item in [*reversed(path.parents), path]:
        if (item.exists() or item.is_symlink()) and is_link(item):
            raise OSError(f'Refusing to write through a symlink or reparse point: {item}')


def tree_snapshot(root, excluded=()):
    result = {}
    excluded = set(excluded)

    def visit(path):
        if path in excluded:
            return
        name = path.relative_to(root).as_posix()
        if is_link(path):
            result[name] = 'link:' + os.readlink(path)
        elif path.is_dir():
            result[name] = 'directory'
            for child in sorted(path.iterdir()):
                visit(child)
        elif path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise OSError(f'Cannot guard special file: {path}')

    if root.exists() or root.is_symlink():
        visit(root)
    return result


def changed_paths(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def mark_integrity_violation(evidence, changed):
    path = evidence / INTEGRITY_MARKER
    plain_path(path)
    evidence.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'reason': 'evidence_changed', 'changed_files': changed}, indent=2) + '\n',
                    encoding='utf-8')


def check_integrity(root):
    path = root / '.harness' / INTEGRITY_MARKER
    plain_path(path)
    if path.exists():
        raise ValueError(f'Evidence integrity violation: inspect {path} and the changed evidence; '
                         'repair or quarantine affected records before removing the marker and rerunning checks.')
