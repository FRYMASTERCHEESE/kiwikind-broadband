"""Temporary exact-hash source transfer; only runs on the isolated integration branch.

The files are locally tested source, not live account data. No provider keys,
network calls or production mutations occur here. This helper is removed after
its source edits are committed and ordinary PR checks then review the result.
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get('GITHUB_REF') != 'refs/heads/integration/stripe-current-stack':
    raise SystemExit('Refusing to edit any other branch.')
changes = json.loads((ROOT/'scripts/integration-edits.json').read_text())
expected = json.loads((ROOT/'scripts/integration-expected.json').read_text())
prepared = {}
for name, spec in changes.items():
    path = (ROOT/name).resolve()
    if not path.is_relative_to(ROOT) or name.startswith(('.git/', '.github/')) or name == '.env':
        raise SystemExit('Forbidden source path.')
    before = path.read_bytes()
    if hashlib.sha256(before).hexdigest() != spec['sha256_before']:
        raise SystemExit('Source changed; manual reconciliation required: '+name)
    text = before.decode('utf-8')
    for start, end, replacement in reversed(spec['edits']):
        if not 0 <= start <= end <= len(text):
            raise SystemExit('Invalid source edit: '+name)
        text = text[:start] + replacement + text[end:]
    result = text.encode('utf-8')
    if hashlib.sha256(result).hexdigest() != spec['sha256_after']:
        raise SystemExit('Edited source checksum mismatch: '+name)
    prepared[name] = result
for name, digest in expected.items():
    path = (ROOT/name).resolve()
    if not path.is_relative_to(ROOT):
        raise SystemExit('Forbidden validation path.')
    data = prepared[name] if name in prepared else path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit('Transferred source differs from locally tested version: '+name)
for name, data in prepared.items():
    (ROOT/name).write_bytes(data)
print('Exact locally tested source verified and applied; no secrets or provider data used.')
