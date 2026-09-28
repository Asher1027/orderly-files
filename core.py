"""Local file organization with exclusive moves and persistent undo journals."""
from __future__ import annotations

import ctypes
import json
import os
import stat
import uuid
import errno
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

GROUPS = {
    '图片': 'jpg jpeg png gif webp bmp svg ico heic tif tiff avif',
    '文档': 'pdf doc docx txt md rtf odt epub typ tex',
    '表格': 'xls xlsx csv tsv ods',
    '演示文稿': 'ppt pptx odp',
    '视频': 'mp4 mov avi mkv webm wmv m4v',
    '音频': 'mp3 wav flac aac m4a ogg opus',
    '压缩包': 'zip rar 7z tar gz bz2 xz',
    '代码': 'py js ts jsx tsx html css json yaml yml toml ipynb c cpp h java rs go sql',
    '安装程序': 'exe msi msix appx',
}
EXTENSIONS = {ext: group for group, values in GROUPS.items() for ext in values.split()}


def signature(path: Path) -> list[int]:
    s = path.stat()
    return [s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino]


def regular(path: Path) -> bool:
    s = path.lstat()
    return stat.S_ISREG(s.st_mode) and not (getattr(s, 'st_file_attributes', 0) & 0x400)


def plan(folder: str, mode: str = 'type', extensions: str = '') -> dict:
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('请选择一个文件夹。')
    allowed = {v.strip().lower().lstrip('.') for v in extensions.replace('，', ',').split(',') if v.strip()}
    rows, skipped, reserved = [], 0, set()
    for source in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        try:
            if not regular(source) or source.name.startswith('.') or source.suffix.lower() in {'.tmp', '.part', '.crdownload'}:
                skipped += 1
                continue
            ext = source.suffix.lower().lstrip('.')
            if allowed and ext not in allowed:
                skipped += 1
                continue
            fingerprint = signature(source)
            month = datetime.fromtimestamp(source.stat().st_mtime).strftime('%Y-%m')
            group = EXTENSIONS.get(ext, '其他文件' if ext else '无扩展名')
            category = Path(month) if mode == 'date' else Path(group)
            if mode == 'type_date':
                category /= month
            target = root / category / source.name
            number = 2
            while target.exists() or target.is_symlink() or str(target).casefold() in reserved:
                target = root / category / f'{source.stem} ({number}){source.suffix}'
                number += 1
            reserved.add(str(target).casefold())
            rows.append({'source': str(source), 'target': str(target), 'signature': fingerprint, 'size': fingerprint[0]})
        except OSError:
            skipped += 1
    return {'root': str(root), 'rows': rows, 'skipped': skipped}


def validate(root: Path, path: Path) -> None:
    if root.resolve() != root or root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('文件夹路径已变化或包含链接。')
    if not path.resolve().is_relative_to(root):
        raise ValueError('目标路径超出选定文件夹。')
    for parent in [path.parent, *path.parent.parents]:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and getattr(parent, 'is_junction', lambda: False)()):
            raise ValueError('分类目录包含链接，已停止该操作。')


def move_exclusive(source: Path, target: Path) -> None:
    # Windows MoveFileW refuses to replace an existing file, even after preview.
    if os.name == 'nt':
        move = ctypes.WinDLL('kernel32', use_last_error=True).MoveFileW
        move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move.restype = ctypes.c_int
        if not move(str(source), str(target)):
            error = ctypes.get_last_error()
            if error != 17:
                raise ctypes.WinError(error)
            copy_move(source, target)
    else:
        try:
            os.link(source, target)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            copy_move(source, target)
        else:
            source.unlink()


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_move(source: Path, target: Path) -> None:
    before = signature(source)
    created = False
    try:
        with source.open('rb') as src, target.open('xb') as dst:
            created = True
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if signature(source) != before or digest(source) != digest(target):
            raise ValueError('复制期间源文件发生变化，已保留源文件。')
        shutil.copystat(source, target)
        source.unlink()
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise


class Organizer:
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir
        history_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: dict) -> None:
        dest = self.history_dir / (record['id'] + '.json')
        tmp = dest.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(dest)

    def history(self) -> list[dict]:
        records = []
        for path in self.history_dir.glob('*.json'):
            try:
                records.append(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError, OSError):
                continue
        return sorted(records, key=lambda r: r['time'], reverse=True)

    def execute(self, preview: dict, progress=None) -> dict:
        root = Path(preview['root'])
        record = {'id': uuid.uuid4().hex, 'time': datetime.now().isoformat(timespec='seconds'), 'root': str(root), 'items': []}
        self.save(record)
        total = len(preview['rows'])
        for index, row in enumerate(preview['rows'], 1):
            if progress:
                progress(index - 1, total, Path(row['source']).name)
            item = dict(row, status='pending', error='')
            record['items'].append(item)
            # Journal before moving so an interruption can be recovered.
            self.save(record)
            try:
                source, target = Path(item['source']), Path(item['target'])
                validate(Path(item.get('source_root', str(root))), source)
                validate(root, target)
                if not regular(source) or signature(source) != item['signature']:
                    raise ValueError('文件在预览后发生变化，请重新预览。')
                item['digest'] = digest(source)
                if signature(source) != item['signature']:
                    raise ValueError('读取期间文件发生变化，请重新预览。')
                self.save(record)
                target.parent.mkdir(parents=True, exist_ok=True)
                validate(root, target)
                move_exclusive(source, target)
                item['target_signature'] = signature(target)
                item['status'] = 'moved'
            except (OSError, ValueError) as exc:
                item.update(status='failed', error=str(exc))
            self.save(record)
            if progress:
                progress(index, total, Path(row['source']).name)
        return record

    def undo(self, record: dict) -> tuple[int, list[str]]:
        restored, errors = 0, []
        root = Path(record['root'])
        for item in reversed(record['items']):
            if item['status'] not in {'moved', 'pending'}:
                continue
            source, target = Path(item['source']), Path(item['target'])
            try:
                validate(Path(item.get('source_root', str(root))), source)
                validate(root, target)
                if item['status'] == 'pending' and source.exists() and not target.exists():
                    item['status'] = 'cancelled'
                    self.save(record)
                    continue
                expected = item.get('target_signature', item['signature'])
                matches = regular(target) and signature(target) == expected
                if item['status'] == 'pending' and item.get('digest') and not source.exists():
                    matches = regular(target) and digest(target) == item['digest']
                if not matches or (item.get('digest') and digest(target) != item['digest']):
                    raise ValueError('整理后的文件已变化，未自动恢复。')
                source.parent.mkdir(parents=True, exist_ok=True)
                move_exclusive(target, source)
                item['status'] = 'undone'
                restored += 1
                self.save(record)
            except (OSError, ValueError) as exc:
                errors.append(f'{source.name}：{exc}')
        return restored, errors
