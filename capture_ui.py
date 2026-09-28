"""Capture only this application's windows, using temporary sample data."""
import tempfile
import time
from pathlib import Path
from PIL import ImageGrab
from app import App
from management_ui import ProfileEditor
from managed import transfer_plan


def capture(window, name):
    window.update()
    window.lift()
    window.attributes('-topmost', True)
    window.update()
    time.sleep(0.4)
    window.update()
    box = (window.winfo_rootx(), window.winfo_rooty(), window.winfo_rootx() + window.winfo_width(), window.winfo_rooty() + window.winfo_height())
    ImageGrab.grab(bbox=box).save(str(Path(__file__).parent / (name + '.png')))


with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    app = App(data_dir=base / 'settings')
    try:
        manager = app.management
        profile = {'id': 'demo', 'name': '工作资料', 'path': str(base / '工作资料'), 'standard': '文件类型', 'rules': [{'name': '文档', 'match': 'pdf,docx'}, {'name': '图片', 'match': 'jpg,png'}], 'fallback': '其他文件'}
        manager.registry.save(profile)
        manager.registry.save(dict(profile,id='study',name='学习资料',path=str(base/'学习资料')))
        manager.registry.save(dict(profile,id='photos',name='图片素材',path=str(base/'图片素材')))
        manager.registry.save(dict(profile,id='personal',name='个人归档',path=str(base/'个人归档')))
        manager.refresh('demo')
        app.update()
        source = base / '待整理'
        source.mkdir()
        for name in ('项目说明.pdf', '设计稿.png', '会议纪要.docx'):
            (source / name).write_text('sample')
        manager.source.set(str(source))
        manager.accept_paths([str(p) for p in source.iterdir()])
        app.update()
        manager.render(transfer_plan(profile, folder=str(source)))
        capture(app, 'preview-managed')
        app.attributes('-topmost', False)
        editor = ProfileEditor(manager, profile)
        capture(editor, 'preview-rules')
        editor.toggle_advanced()
        capture(editor, 'preview-rules-advanced')
        editor.destroy()
        app.tabs.select(1)
        capture(app, 'preview-local')
        app.attributes('-topmost',False)
        app.show_history()
        capture(app.history_window,'preview-history')
    finally:
        app.destroy()
