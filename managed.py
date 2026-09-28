"""Managed destinations and deterministic, user-defined classification."""
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from core import GROUPS, regular, signature, validate

STANDARDS = ['文件类型', '文件名关键词', '修改月份', '扩展名']


def safe_name(name):
    if not name or name in {'.', '..'} or name != name.strip() or name.endswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError(f'子文件夹名称无效：{name!r}')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(f'Windows 保留名称：{name}')
    return name


def preset(standard):
    if standard == '文件类型':
        return [{'name': name, 'match': values.replace(' ', ',')} for name, values in GROUPS.items()]
    if standard == '文件名关键词':
        return [{'name': '合同', 'match': '合同,协议'}, {'name': '发票', 'match': '发票,收据'}]
    if standard == '修改月份':
        month = datetime.now().strftime('%Y-%m')
        return [{'name': month, 'match': month}]
    return [{'name': 'PDF', 'match': 'pdf'}, {'name': '图片', 'match': 'jpg,png,webp'}]


def check_profile(profile):
    if profile['standard'] not in STANDARDS:
        raise ValueError('请选择分类标准。')
    names = set()
    for row in profile['rules']:
        key = safe_name(row['name']).casefold()
        if key in names:
            raise ValueError('子文件夹名称不能重复。')
        names.add(key)
        terms = split_terms(row['match'])
        if profile['standard'] == '修改月份' and any(not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', t) for t in terms):
            raise ValueError('月份请填写 YYYY-MM，例如 2026-09。')
    fallback = safe_name(profile['fallback'])
    if fallback.casefold() in names:
        raise ValueError('未匹配文件夹需使用单独的名称。')


def split_terms(value):
    return [s.strip().casefold() for s in re.split(r'[,，;；\n]', value) if s.strip()]


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []

    def save(self, profile):
        check_profile(profile)
        root = Path(profile['path']).expanduser().resolve()
        for other in self.profiles:
            if other['id'] != profile['id'] and Path(other['path']) == root:
                raise ValueError('这个文件夹已经被托管。')
        names = [r['name'] for r in profile['rules']] + [profile['fallback']]
        for name in names:
            validate(root, root / name / '__check__')
            child = root / name
            if child.exists() and not child.is_dir():
                raise ValueError(f'存在同名文件，无法创建子文件夹：{name}')
        root.mkdir(parents=True, exist_ok=True)
        for name in names:
            (root / name).mkdir(exist_ok=True)
        saved = dict(profile, path=str(root))
        updated = [p for p in self.profiles if p['id'] != saved['id']] + [saved]
        self.write(updated)
        return saved

    def write(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as stream:
            json.dump(profiles, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(self.path)
        self.profiles = profiles

    def remove(self, profile_id):
        self.write([p for p in self.profiles if p['id'] != profile_id])


def category(source, profile):
    standard = profile['standard']
    value = source.suffix.lower().lstrip('.') if standard in {'文件类型', '扩展名'} else source.name.casefold()
    if standard == '修改月份':
        value = datetime.fromtimestamp(source.stat().st_mtime).strftime('%Y-%m')
    for rule in profile['rules']:
        terms = split_terms(rule['match'])
        if standard == '文件名关键词':
            matched = any(term in value for term in terms)
        else:
            matched = value in [term.lstrip('.') for term in terms]
        if matched:
            return rule['name']
    return profile['fallback']


def transfer_plan(profile, folder=None, files=None, recursive=False, extensions=''):
    check_profile(profile)
    root = Path(profile['path']).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('托管目标不是文件夹。')
    candidates, skipped = [], 0
    if folder:
        origin = Path(folder).resolve(strict=True)
        if not origin.is_dir():
            raise ValueError('来源不是文件夹。')
        if origin == root or origin.is_relative_to(root) or root.is_relative_to(origin):
            raise ValueError('批量迁移的来源和目标不能相同或互相包含。请使用原位整理或选择独立文件夹。')
        if recursive:
            def walk_error(error):
                raise error
            for parent, dirs, names in os.walk(origin, followlinks=False, onerror=walk_error):
                kept = [d for d in dirs if not d.startswith('.') and not (Path(parent) / d).is_symlink() and not getattr(Path(parent) / d, 'is_junction', lambda: False)()]
                skipped += len(dirs) - len(kept)
                dirs[:] = kept
                candidates.extend(Path(parent) / n for n in names)
        else:
            candidates = list(origin.iterdir())
    else:
        candidates = [Path(p).absolute() for p in (files or [])]
    allowed = {t.lstrip('.') for t in split_terms(extensions)}
    rows, reserved, seen = [], set(), set()
    for source in sorted(candidates, key=lambda p: str(p).casefold()):
        if str(source).casefold() in seen:
            continue
        seen.add(str(source).casefold())
        try:
            if not regular(source) or source.name.startswith('.') or source.suffix.lower() in {'.tmp', '.part', '.crdownload'}:
                skipped += 1
                continue
            if allowed and source.suffix.casefold().lstrip('.') not in allowed:
                skipped += 1
                continue
            source = source.resolve(strict=True)
            dest_dir = root / category(source, profile)
            validate(root, dest_dir / source.name)
            if source.parent == dest_dir:
                skipped += 1
                continue
            target = dest_dir / source.name
            number = 2
            while target.exists() or target.is_symlink() or str(target).casefold() in reserved:
                target = dest_dir / f'{source.stem} ({number}){source.suffix}'
                number += 1
            reserved.add(str(target).casefold())
            sig = signature(source)
            rows.append({'source': str(source), 'source_root': str(origin if folder else source.parent), 'target': str(target), 'signature': sig, 'size': sig[0]})
        except OSError:
            skipped += 1
    return {'root': str(root), 'rows': rows, 'skipped': skipped}


def import_plan(profile, paths, recursive=False, extensions=''):
    """Combine a mixed Explorer drop into one collision-free transaction."""
    rows, seen, reserved, skipped = [], set(), set(), 0
    root = Path(profile['path']).resolve(strict=True)
    for raw in paths:
        path = Path(raw).expanduser().absolute()
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            skipped += 1
            continue
        if not path.exists():
            raise ValueError(f'路径不存在：{path}')
        part = transfer_plan(profile, folder=str(path) if path.is_dir() else None, files=None if path.is_dir() else [str(path)], recursive=recursive, extensions=extensions)
        skipped += part['skipped']
        for row in part['rows']:
            key = row['source'].casefold()
            if key in seen:
                continue
            seen.add(key)
            target, source = Path(row['target']), Path(row['source'])
            number = 2
            while target.exists() or target.is_symlink() or str(target).casefold() in reserved:
                target = target.parent / f'{source.stem} ({number}){source.suffix}'
                number += 1
            row['target'] = str(target)
            reserved.add(str(target).casefold())
            rows.append(row)
    return {'root': str(root), 'rows': rows, 'skipped': skipped}
