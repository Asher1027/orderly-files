"""Generate harmless fixtures. Existing files with different content are never overwritten."""
from __future__ import annotations

import io
import math
import os
import struct
import wave
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
OLD = datetime(2025, 4, 15, 10, 30).timestamp()
NEW = datetime(2026, 9, 12, 15, 45).timestamp()


def save(relative, data, modified=None):
    path = BASE / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = data.encode('utf-8') if isinstance(data, str) else data
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f'不会覆盖已有文件：{path}')
    else:
        path.write_bytes(data)
    if modified:
        os.utime(path, (modified, modified))


def png():
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body))
    width, height = 96, 64
    raw = b''.join(b'\x00' + b'\x79\x9a\xe8' * width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def pdf():
    stream = b'BT /F1 20 Tf 50 740 Td (File organizer test) Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        frames = [int(2500 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(1600)]
        handle.writeframes(struct.pack('<' + 'h' * len(frames), *frames))
    return buffer.getvalue()


def zipped():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as handle:
        handle.writestr('说明.txt', '可解压的测试压缩包。')
    return buffer.getvalue()


def create():
    document, image, audio, archive = pdf(), png(), wav(), zipped()
    csv = '\ufeff项目,金额\n资料整理,128.50\n图像采集,36.00\n'.encode('utf-8')
    root = '01_原位整理/下载区'
    for name, content, date in [
        ('项目说明.pdf', document, OLD), ('会议纪要.TXT', '原位整理与大小写。', NEW),
        ('费用明细.csv', csv, NEW), ('封面.PNG', image, OLD),
        ('提示音.wav', audio, NEW), ('资料备份.zip', archive, OLD),
        ('示例脚本.py', 'print("fixture")\n', NEW),
        ('未知格式.xyz', '测试其他文件分类。', NEW),
        ('无扩展名', '测试无扩展名分类。', OLD),
        ('.隐藏文件.txt', '应跳过。', NEW), ('下载中.part', '应跳过。', NEW),
        ('缓存.tmp', '应跳过。', NEW), ('未完成.crdownload', '应跳过。', NEW),
    ]:
        save(f'{root}/{name}', content, date)
    save(f'{root}/图片/封面.PNG', '原本就在目标位置的占位文件，不能覆盖。')
    save(f'{root}/已有子文件夹/里面的文档.pdf', document)

    a, b = '02_托管迁移/来源_甲', '02_托管迁移/来源_乙'
    for path, content, date in [
        (f'{a}/公共说明.pdf', document, OLD),
        (f'{a}/计划.txt', '来自甲。', NEW),
        (f'{a}/素材.png', image, NEW),
        (f'{a}/子目录一/同名记录.txt', '甲的一号记录。', OLD),
        (f'{a}/子目录二/同名记录.txt', '甲的二号记录。', NEW),
        (f'{a}/空目录/.保留标记', '空目录应保留。', NEW),
        (f'{b}/公共说明.pdf', document, NEW),
        (f'{b}/另一份计划.txt', '来自乙。', OLD),
        (f'{b}/子目录/资料备份.zip', archive, NEW),
    ]:
        save(path, content, date)

    save('03_托管目标/工作资料/文档/公共说明.pdf', '原目标文件，不应覆盖。')
    save('03_托管目标/工作资料/保留原内容.txt', '原有文件应保持不变。')
    save('03_托管目标/学习资料/原有笔记.md', '# 原有笔记\n托管后应保留。\n')

    for name, content, date in [
        ('来自桌面_合同.pdf', document, NEW),
        ('来自下载_图片.png', image, OLD),
        ('来自其他地方_清单.csv', csv, NEW),
        ('无扩展名的单文件', '进入兜底目录。', NEW),
    ]:
        save(f'04_单文件导入/{name}', content, date)

    rules = '05_自定义规则'
    for path, content, date in [
        ('关键词/合同_采购.pdf', document, NEW),
        ('关键词/协议_服务.pdf', document, NEW),
        ('关键词/发票_九月.csv', csv, NEW),
        ('关键词/普通备忘录.txt', '不含关键词。', NEW),
        ('月份/2025年旧资料.txt', '修改时间为2025-04。', OLD),
        ('月份/2026年新资料.txt', '修改时间为2026-09。', NEW),
        ('扩展名/大写图片.JPG', '仅用于扩展名测试，不是真实JPEG。', NEW),
        ('扩展名/小写图片.png', image, NEW),
        ('扩展名/报告.PDF', document, NEW),
        ('扩展名/未匹配.data', '进入兜底目录。', NEW),
    ]:
        save(f'{rules}/{path}', content, date)

    save('06_安全与撤销/预览后修改.txt', '预览后修改这个文件，再确认迁移。', NEW)
    save('06_安全与撤销/撤销前占位.txt', '迁移后在原位置新建同名文件，再撤销。', NEW)
    save('06_安全与撤销/整理后修改.txt', '迁移后修改目标文件，再撤销。', NEW)
    samples = [p for p in BASE.rglob('*') if p.is_file() and p.parent != BASE]
    print(f'已生成 {len(samples)} 个样例文件：{BASE}')


if __name__ == '__main__':
    create()
