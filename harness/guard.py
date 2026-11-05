"""Change detection; this is not an operating-system sandbox."""

import hashlib
import json
import os
import stat
import time


INTEGRITY_MARKER = 'integrity-violation.json'
REPARSE_POINT = 0x400
# Coarse file systems (FAT) store 2-second timestamps: a file written that recently could change
# again without a visible timestamp change, so its digest is never reused.
SETTLE_NS = 2_000_000_000
_digests = {}


def is_link(path):
    return is_link_info(path.lstat())


def is_link_info(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & REPARSE_POINT)


def signature(info):
    """What must stay equal for a cached digest to be reused.

    POSIX ctime changes on every write or timestamp change and user code cannot set it back.
    Windows exposes no such field, so there only size and modification time are compared.
    """
    if os.name == 'nt':
        return info.st_size, info.st_mtime_ns
    return info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev


def file_digest(path, info):
    key = os.fspath(path)
    mark = signature(info)
    known = _digests.get(key)
    if known is not None and known[0] == mark:
        return known[1]
    with open(path, 'rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    newest = info.st_mtime_ns if os.name == 'nt' else max(info.st_mtime_ns, info.st_ctime_ns)
    if newest < time.time_ns() - SETTLE_NS:
        _digests[key] = (mark, value)
    else:
        _digests.pop(key, None)
    return value


def plain_path(path):
    for item in [*reversed(path.parents), path]:
        if (item.exists() or item.is_symlink()) and is_link(item):
            raise OSError(f'Refusing to write through a symlink or reparse point: {item}')


def tree_snapshot(root, excluded=()):
    """Map each path to 'directory', 'link:<target>' or the SHA-256 of its content.

    Files are hashed in a stream. A digest is reused only within this process and only while the
    file's signature is unchanged and older than SETTLE_NS.
    """
    result = {}
    base = os.fspath(root)
    # normcase keeps Windows' case-insensitive path equality, as pathlib comparisons had.
    skip = {os.path.normcase(os.fspath(path)) for path in excluded}
    if not (root.exists() or root.is_symlink()) or os.path.normcase(base) in skip:
        return result
    start = len(base.rstrip(os.sep)) + 1
    # Plain strings keep this loop cheap: it visits every file of the project for each AI call.
    pending = [(base, root.lstat())]
    while pending:
        path, info = pending.pop()
        name = '.' if path == base else path[start:].replace(os.sep, '/')
        if is_link_info(info):
            result[name] = 'link:' + os.readlink(path)
        elif stat.S_ISDIR(info.st_mode):
            result[name] = 'directory'
            with os.scandir(path) as entries:
                pending.extend((entry.path, entry.stat(follow_symlinks=False))
                               for entry in entries if os.path.normcase(entry.path) not in skip)
        elif stat.S_ISREG(info.st_mode):
            result[name] = file_digest(path, info)
        else:
            raise OSError(f'Cannot guard special file: {path}')
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
