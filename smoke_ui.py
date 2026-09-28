"""Exercise desktop workflows against temporary files only."""
import tempfile
import time
from types import SimpleNamespace
from pathlib import Path

from app import App
from management_ui import ProfileEditor
from watcher import WatchScanner


def run():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        app = App(data_dir=base / 'settings')
        errors = []
        app.report_callback_exception = lambda *error: errors.append(error)
        try:
            app.update()
            manager = app.management
            assert not hasattr(manager,'hero')
            app.update()
            assert manager.import_bar.master is manager.pending_shell.content
            assert manager.import_bar.winfo_rooty() >= manager.pending.winfo_rooty()+manager.pending.winfo_height()
            assert [w for w in manager.card_inner.winfo_children() if not getattr(w,'_wave_layer',False)][-1] is manager.add_card
            manager.add_card.choose()
            app.update()
            opened=[w for w in app.winfo_children() if isinstance(w,ProfileEditor)]
            assert len(opened)==1
            opened[0].destroy()
            editor = ProfileEditor(manager)
            app.update()
            assert not editor.advanced.winfo_manager()
            editor.toggle_advanced()
            app.update()
            assert editor.advanced.winfo_manager()
            assert editor.advanced_canvas.winfo_exists()
            editor.toggle_advanced()
            existing=base/'已有 资料夹'
            existing.mkdir()
            sample=existing/'保留.txt'
            sample.write_text('keep')
            def drop_data(*paths):
                return SimpleNamespace(data=app.tk.call('format','%s',app.tk.call('list',*[str(p) for p in paths])))
            assert editor.drop_existing_folder(drop_data(existing))=='copy'
            assert editor.name.get()==existing.name
            assert Path(editor.path.get())==existing
            assert not manager.registry.profiles
            assert list(existing.iterdir())==[sample]
            assert editor.drop_existing_folder(drop_data(sample))=='refuse_drop'
            assert editor.drop_existing_folder(drop_data(existing,base))=='refuse_drop'
            assert Path(editor.path.get())==existing
            editor.name.set('测试托管')
            editor.path.set(str(base / 'archive'))
            editor.fill([{'name': '资料', 'match': 'pdf,txt'}])
            editor.quantity.set('2')
            editor.bulk()
            assert len(editor.rules.get_children()) == 3
            editor.save()
            app.update()
            assert len(manager.registry.profiles) == 1
            assert [w for w in manager.card_inner.winfo_children() if not getattr(w,'_wave_layer',False)][-1] is manager.add_card
            assert len(list((base / 'archive').iterdir())) == 4
            source = base / 'inbox'
            source.mkdir()
            (source / '报告.pdf').write_text('example')
            manager.folder = str(source)
            manager.scan()
            pump(app)
            manager.show_preview()
            app.update()
            assert len(manager.items.get_children()) == 1
            manager.preview_window.event_generate('<<Unused>>')
            manager.preview_window.withdraw()
            manager.show_preview()
            app.update()
            assert len(manager.items.get_children()) == 1
            manager.execute()
            pump(app)
            assert (base / 'archive/资料/报告.pdf').exists()
            assert not (source / '报告.pdf').exists()
            app.show_history()
            app.update()
            history=app.history_window
            history.geometry(f'{history.minsize()[0]}x{history.minsize()[1]}')
            app.update()
            button=history.undo_button
            assert button.winfo_ismapped()
            assert button.winfo_rooty()+button.winfo_height()<=history.winfo_rooty()+history.winfo_height()
            assert str(app.tk.call('package','require','tkdnd'))
            record = app.engine.history()[0]
            app.worker(lambda: app.engine.undo(record), app.undone)
            pump(app)
            assert (source / '报告.pdf').exists()
            new_target=base/'拖入创建托管'
            new_target.mkdir()
            assert manager.add_card.drop(drop_data(new_target))=='copy'
            app.update()
            assert manager.selected()['path']==str(new_target)
            assert (new_target/'其他文件').is_dir()
            direct_file=base/'一步迁移.txt'
            direct_file.write_text('direct')
            manager.accept_paths([str(direct_file)])
            manager.direct_migrate()
            pump(app)
            assert not direct_file.exists()
            assert (new_target/'文档'/'一步迁移.txt').exists()
            assert any(r['items'] for r in app.engine.history())
            assert app.last_record is not None
            assert str(app.result_btn.cget('state'))=='normal'
            app.show_record_details(app.last_record)
            app.update()
            details=[w for w in app.winfo_children() if getattr(w,'title',lambda:None)()=='操作明细']
            assert details
            details[0].destroy()
            manager.clear_pending()
            manager.select_target(next(p['id'] for p in manager.registry.profiles if p['path']==str(base/'archive')))
            # Dispatch through the registered card's drop handler, including a
            # Tcl list containing spaces and Chinese characters.
            single=base/'拖入 测试.txt'
            single.write_text('drag sample')
            card=next(iter(manager.cards.values()))
            payload=app.tk.call('format','%s',app.tk.call('list',str(single),str(source)))
            assert card.drop(SimpleNamespace(data=payload))=='copy'
            pump(app)
            assert len(manager.preview['rows'])==2
            assert single.exists(), 'Drop must only preview, never move implicitly'
            manager.clear_pending()
            manager.accept_paths([str(single),str(single)])
            app.update()
            assert len(manager.paths)==1
            assert manager.preview is None
            assert single.exists()
            manager.remove_pending()
            app.update()
            assert not manager.paths
            assert single.exists(), 'Removing a queue item must not delete its file'
            app.tabs.select(1)
            app.folder.set(str(source))
            app.scan()
            pump(app)
            assert len(app.tree.get_children()) == 1
            app.geometry(f'{app.minsize()[0]}x{app.minsize()[1]}')
            app.tabs.select(0)
            end=time.monotonic()+0.3
            while time.monotonic()<end:
                app.update()
                time.sleep(0.015)
            assert manager.execute_btn.winfo_ismapped()
            assert manager.execute_btn.winfo_rooty()+manager.execute_btn.winfo_height()<=app.winfo_rooty()+app.winfo_height()
            app.preview_btn.animate(True)
            end=time.monotonic()+0.2
            while time.monotonic()<end:
                app.update()
                time.sleep(0.015)
            assert app.preview_btn.progress>.9
            manager.show_watchers()
            app.update()
            watcher_windows=[w for w in app.winfo_children() if getattr(w,'title',lambda:None)()=='自动监视']
            assert watcher_windows and watcher_windows[0].watch_tree.winfo_exists()
            watcher_windows[0].destroy()
            watched_source=base/'自动监视来源'
            watched_source.mkdir()
            watched_file=watched_source/'自动报告.txt'
            watched_file.write_text('watched')
            watch={'id':'watch-test','source':str(watched_source),'profile_id':manager.selected_id,'enabled':True}
            manager.watches.append(watch)
            manager.watch_store.save_watches(manager.watches)
            manager.watch_scanner=WatchScanner(settle_seconds=0,clock=lambda:0)
            manager.watch_scanner.ready([watch])
            app.after_cancel(manager._watch_timer)
            manager.watch_tick()
            pump(app)
            assert not watched_file.exists()
            assert (base/'archive'/'资料'/'自动报告.txt').exists()
            manager.accept_paths([str(single)])
            assert manager.session_store.load()['paths']==[str(single)]
            assert not errors, errors
        finally:
            app.destroy()
        resumed=App(data_dir=base/'settings')
        try:
            resumed.update()
            assert resumed.management.paths==[str(single)]
            assert resumed.management.target_text.get().startswith('目标：')
            print('PASS: scrollable rules, direct migration, progress/result UI, watch UI, pending restart, undo, native DnD')
        finally:
            resumed.destroy()


def pump(app):
    app.update()
    end = time.monotonic() + 15
    while app.busy and time.monotonic() < end:
        app.update()
        time.sleep(0.02)
    app.update()
    assert not app.busy, 'UI operation timed out'


if __name__ == '__main__':
    run()
