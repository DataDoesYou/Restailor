#!/usr/bin/env python
"""Migration sanity checks.

Fail fast if:
- Any revision id length > 32 (alembic_version.version_num is VARCHAR(32)).
- Any down_revision / merge dependency references a missing revision file.
- Duplicate revision ids (should not happen).

Exit codes:
 0 OK
 1 Issues found (they are printed in a concise machine-parsable format)

Intended usage (CI):
  python scripts/check_migrations.py
"""
from __future__ import annotations
import sys, re, os, json

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'alembic', 'versions')

REV_PATTERN_PRIMARY = re.compile(r'^revision\s*=\s*[\"\']([^\"\']+)[\"\']', re.MULTILINE)
REV_PATTERN_TYPED = re.compile(r'^revision\s*:\s*str\s*=\s*[\"\']([^\"\']+)[\"\']', re.MULTILINE)
DOWN_PATTERN = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)
DOWN_PATTERN_TYPED = re.compile(r'^down_revision\s*:\s*[^=]*=\s*(.+)$', re.MULTILINE)

def run_checks() -> dict:
    """Run migration sanity checks and return result dict.

    Returns dict keys:
      total_revisions: int
      issues: list[dict]
    """
    issues: list[dict] = []
    rev_to_file: dict[str, str] = {}
    rev_to_downs: dict[str, list[str]] = {}

    if not os.path.isdir(VERSIONS_DIR):
        return {'error': 'versions_dir_missing', 'path': VERSIONS_DIR, 'issues': [{'type': 'versions_dir_missing'}]}

    for fn in os.listdir(VERSIONS_DIR):
        if not fn.endswith('.py'):
            continue
        path = os.path.join(VERSIONS_DIR, fn)
        try:
            txt = open(path, 'r', encoding='utf-8').read()
        except OSError as ex:
            issues.append({'type': 'read_error', 'file': fn, 'msg': str(ex)})
            continue
        m = REV_PATTERN_PRIMARY.search(txt) or REV_PATTERN_TYPED.search(txt)
        if not m:
            continue  # allow stub/non-standard files
        rev = m.group(1).strip()
        if rev in rev_to_file:
            issues.append({'type': 'duplicate_revision', 'rev': rev, 'files': [rev_to_file[rev], fn]})
        rev_to_file[rev] = fn
        if len(rev) > 32:
            issues.append({'type': 'long_revision_id', 'rev': rev, 'length': len(rev), 'file': fn})
        dm = DOWN_PATTERN.search(txt) or DOWN_PATTERN_TYPED.search(txt)
        if dm:
            raw = dm.group(1).split('#')[0].strip()
            downs: list[str] = []
            if raw.startswith(('(', '[')):
                inner = raw.strip('()[]')
                for part in inner.split(','):
                    part = part.strip().strip('\"\'')
                    if part:
                        downs.append(part)
            elif raw in ('None', 'None,'):
                downs = []
            else:
                downs = [raw.strip().strip('\"\'')]
            rev_to_downs[rev] = downs

    # Validate referenced downs
    for rev, downs in rev_to_downs.items():
        for d in downs:
            if d and d not in rev_to_file:
                issues.append({'type': 'missing_dependency', 'rev': rev, 'missing': d})

    return {
        'total_revisions': len(rev_to_file),
        'issues': issues,
    }


def _main() -> int:
    result = run_checks()
    print(json.dumps({k: v for k, v in result.items() if k in ('total_revisions', 'issues')}, indent=2, sort_keys=True))
    issues = result.get('issues', [])
    if issues:
        for i in issues:
            print(f"ISSUE: {i['type']} -> {i}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(_main())
