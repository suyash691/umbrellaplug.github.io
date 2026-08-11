#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path('omega/plugin.video.umbrella')
LIB = ROOT / 'resources/lib'
DEEPBRID = LIB / 'debrid/deepbrid.py'
DB_CLOUD = LIB / 'cloud_scrapers/db_cloud.py'
NAVIGATOR = LIB / 'menus/navigator.py'
ROUTER = LIB / 'modules/router.py'
SOURCES = LIB / 'modules/sources.py'
SETTINGS = ROOT / 'resources/settings.xml'
SERVICE = ROOT / 'service.py'
CLOUD_INIT = LIB / 'cloud_scrapers/__init__.py'
DEBRID_MODULE = LIB / 'modules/debrid.py'
SOURCE_RESULTS = LIB / 'windows/source_results.py'


def text(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def section(title: str) -> None:
    print('\n' + '=' * 78)
    print(title)
    print('=' * 78)


def is_const_return_stub(fn: ast.FunctionDef) -> bool:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    if value is None:
        return True
    if isinstance(value, ast.Constant) and value.value in (None, False, True, 0, ''):
        return True
    if isinstance(value, (ast.List, ast.Dict, ast.Tuple, ast.Set)) and len(value.elts if hasattr(value, 'elts') else value.keys) == 0:
        return True
    return False


errors = []

section('Repository / Python parse')
py_files = list(ROOT.rglob('*.py'))
print('Python files:', len(py_files))
for path in py_files:
    try:
        ast.parse(text(path), filename=str(path))
    except SyntaxError as exc:
        errors.append(f'Syntax error: {path}: {exc}')
print('AST parse errors:', sum(1 for e in errors if e.startswith('Syntax error:')))

section('settings.xml')
try:
    tree = ET.parse(SETTINGS)
    setting_ids = [node.get('id') for node in tree.findall('.//setting') if node.get('id')]
    duplicates = sorted(k for k, v in Counter(setting_ids).items() if v > 1)
    deepbrid_settings = sorted(x for x in setting_ids if 'deepbrid' in x.lower() or x == 'db_cloud.enabled')
    print('Deepbrid settings:')
    for item in deepbrid_settings:
        print('  ', item)
    print('Duplicate setting IDs:', duplicates or 'none')
    if duplicates:
        errors.append('Duplicate setting IDs: ' + ', '.join(duplicates))
    required = {
        'deepbrid.enable', 'deepbrid.token', 'deepbrid.priority',
        'db_cloud.enabled', 'deepbridexpirynotice', 'deepbrid.notification.range'
    }
    missing = sorted(required.difference(setting_ids))
    print('Missing required Deepbrid settings:', missing or 'none')
    if missing:
        errors.append('Missing settings: ' + ', '.join(missing))
except Exception as exc:
    errors.append(f'settings.xml parse failure: {exc}')

section('Deepbrid AST / unused imports / duplicate methods')
deep_src = text(DEEPBRID)
deep_tree = ast.parse(deep_src)
imports = {}
for node in ast.walk(deep_tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports[alias.asname or alias.name.split('.')[0]] = alias.name
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            imports[alias.asname or alias.name] = f'{node.module}.{alias.name}' if node.module else alias.name
loads = {node.id for node in ast.walk(deep_tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
unused_imports = sorted((name, target) for name, target in imports.items() if name not in loads)
print('Unused imports:', unused_imports or 'none')

classes = [node for node in deep_tree.body if isinstance(node, ast.ClassDef) and node.name == 'Deepbrid']
if len(classes) != 1:
    errors.append(f'Expected one Deepbrid class, found {len(classes)}')
    methods = []
else:
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef)]
method_names = [m.name for m in methods]
dup_methods = sorted(k for k, v in Counter(method_names).items() if v > 1)
print('Deepbrid methods:', len(method_names))
print('Duplicate Deepbrid methods:', dup_methods or 'none')
if dup_methods:
    errors.append('Duplicate Deepbrid methods: ' + ', '.join(dup_methods))

stubs = [m.name for m in methods if is_const_return_stub(m)]
print('Constant-return/stub-like methods:', ', '.join(stubs) if stubs else 'none')

section('Method reference counts (heuristic dead-code check)')
all_py_text = '\n'.join(text(p) for p in py_files)
likely_dead = []
for name in method_names:
    count = len(re.findall(r'\b' + re.escape(name) + r'\b', all_py_text))
    if count <= 1:
        likely_dead.append(name)
    if count <= 2 or name in stubs:
        print(f'{name:34s} occurrences={count}' + ('  [stub]' if name in stubs else ''))
print('Methods only referenced at their definition:', ', '.join(likely_dead) if likely_dead else 'none')

section('Router / navigator symmetry')
nav_src = text(NAVIGATOR)
router_src = text(ROUTER)
nav_actions = sorted(set(re.findall(r"['\"](db_[A-Za-z0-9_]+)", nav_src)))
router_actions = sorted(set(re.findall(r"action\s*==\s*['\"](db_[A-Za-z0-9_]+)['\"]", router_src)))
print('Navigator db actions:', nav_actions)
print('Router db actions:', router_actions)
missing_routes = sorted(set(nav_actions) - set(router_actions))
print('Navigator actions without router handler:', missing_routes or 'none')
if missing_routes:
    errors.append('Navigator db actions missing router handlers: ' + ', '.join(missing_routes))

section('db_cloud registration / resolver wiring')
sources_src = text(SOURCES)
checks = {
    'cloud loader registration': 'db_cloud' in text(CLOUD_INIT),
    'sources cloud list registration': "('deepbrid', 'db_cloud', 'deepbrid')" in sources_src,
    'sources direct resolver registration': "'db_cloud'" in sources_src,
    'db_cloud setting': 'db_cloud.enabled' in text(SETTINGS),
    'db_cloud provider implementation': "'provider': 'db_cloud'" in text(DB_CLOUD),
    'Deepbrid resolver enabled': 'deepbrid.Deepbrid()' in text(DEBRID_MODULE),
    'Deepbrid token convention': "getSetting('%s.token' % debrid_service)" in sources_src,
}
for label, ok in checks.items():
    print(f'{label}: {"OK" if ok else "MISSING"}')
    if not ok:
        errors.append('Missing integration: ' + label)

section('Known unsupported-action guards')
source_results = text(SOURCE_RESULTS)
for phrase in ('showDebridPack', 'saveToCloud'):
    print(phrase, 'present:', phrase in source_results)
print('Deepbrid exclusion references in source_results:', source_results.count('Deepbrid'))
if "debrid != 'Deepbrid' and 'cached (pack)'" not in source_results:
    errors.append('Deepbrid Browse Pack exclusion missing')
if "debrid not in ('EasyDebrid', 'Deepbrid')" not in source_results:
    errors.append('Deepbrid Save-to-Cloud exclusion missing')

section('Suspicious stale symbols / generated artifacts')
suspects = [
    '_deepbrid_file_token', '_is_extra_file', 'list_transfer',
    'parse_qs', "getSetting('db_cloud.enabled') == 'true'"
]
for suspect in suspects:
    locations = []
    for p in py_files:
        if suspect in text(p):
            locations.append(str(p.relative_to(ROOT)))
    print(f'{suspect!r}: {locations or "none"}')

section('Deepbrid service expiry wiring')
service_src = text(SERVICE)
for token in ('deepbridexpirynotice', 'deepbrid.notification.range', "withinRangeCheck('deepbrid'", "datetime.strptime(str(expiration), '%Y-%m-%d')"):
    ok = token in service_src or token in text(SETTINGS)
    print(f'{token}: {"OK" if ok else "MISSING"}')
    if not ok:
        errors.append('Missing expiry integration token: ' + token)

section('Security/logging sanity')
for forbidden in ("'final_url':", "'history': history", "'location': location"):
    present = forbidden in deep_src
    print(f'{forbidden}: {"PRESENT" if present else "absent"}')
    if present:
        errors.append('One-time URL metadata still retained: ' + forbidden)
print('repr(selected) occurrences:', deep_src.count('repr(selected)'))
print('repr(probe) occurrences:', deep_src.count('repr(probe)'))

section('Summary')
print('Hard audit errors:', len(errors))
for err in errors:
    print('ERROR:', err)
if errors:
    sys.exit(1)
print('AUDIT_HARD_CHECKS_OK')
