from __future__ import annotations

import os
import sys
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from tkinterdnd2 import TkinterDnD
from modern import AnimatedButton, AnimatedTabs, RoundedPanel

from core import Organizer, plan

BG, WHITE, INK, MUTED, ACCENT = '#f5f5f7', '#ffffff', '#25272b', '#858b95', '#292c32'


def size_text(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024


def default_data_dir():
    if getattr(sys,'frozen',False):
        executable_dir=Path(sys.executable).resolve().parent
        if (executable_dir/'便携模式.flag').is_file():
            return executable_dir/'用户数据'
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'GuiyiOrganizer'


class App(TkinterDnD.Tk):
    def __init__(self, data_dir=None):
        if os.name == 'nt':
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except OSError:
                pass
        super().__init__()
        self.ui_scale = max(1.0, self.winfo_fpixels('1i') / 96)
        self.title('归序')
        self.logo_path=Path(__file__).parent/'assets'/'guixu-icon.png'
        if self.logo_path.exists():
            self.window_icon=tk.PhotoImage(file=str(self.logo_path))
            self.iconphoto(True,self.window_icon)
        width = min(round(1220 * self.ui_scale), self.winfo_screenwidth() - 80)
        height = min(round(860 * self.ui_scale), self.winfo_screenheight() - 100)
        self.geometry(f'{width}x{height}+40+40')
        self.minsize(min(round(1080 * self.ui_scale), width), min(round(780 * self.ui_scale), height))
        self.configure(bg=BG)
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.engine = Organizer(self.data_dir / 'history')
        self.preview = None
        self.busy = False
        self.events = queue.Queue()
        self.last_record = None
        self.folder = tk.StringVar()
        self.mode = tk.StringVar(value='按文件类型')
        self.filter = tk.StringVar()
        self.status = tk.StringVar(value='选择文件夹后生成预览。')
        self.style_ui()
        self.build()
        from backdrop import WaveBackdrop
        self.backdrop=WaveBackdrop(self,BG)
        for value in (self.folder, self.mode, self.filter):
            value.trace_add('write', self.invalidate)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._poll_timer=self.after(100, self.poll)

    def style_ui(self):
        import tkinter.font as tkfont
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
            tkfont.nametofont(name).configure(family='Microsoft YaHei UI', size=10)
        self.option_add('*font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Treeview', background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=38, borderwidth=0, font=('Microsoft YaHei UI', 10))
        style.configure('Treeview.Heading', background='#f5f6f8', foreground=MUTED, padding=12, relief='flat', borderwidth=0, font=('Microsoft YaHei UI', 10))
        style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        style.map('Treeview', background=[('selected', '#e9eef4')], foreground=[('selected', INK)])
        style.configure('TCombobox', padding=9)
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(24, 12), background='#e9edf3', foreground=MUTED, font=('Microsoft YaHei UI', 10))
        style.map('TNotebook.Tab', background=[('selected', WHITE)], foreground=[('selected', ACCENT)])

    def label(self, parent, text, size=10, color=INK, bold=False, bg=None):
        return tk.Label(parent, text=text, bg=bg or parent.cget('bg'), fg=color, font=('Microsoft YaHei UI', size, 'bold' if bold else 'normal'), anchor='w')

    def button(self, parent, text, command, primary=False):
        return AnimatedButton(parent,text,command,primary)

    def build(self):
        header = tk.Frame(self, bg=BG, padx=26, pady=12)
        header.pack(fill='x')
        if self.logo_path.exists():
            from PIL import Image,ImageTk
            self.header_icon=ImageTk.PhotoImage(Image.open(self.logo_path).resize((40,40),Image.Resampling.LANCZOS),master=self)
            mark=tk.Canvas(header,width=44,height=44,bg=BG,highlightthickness=0,bd=0)
            mark.create_image(22,22,image=self.header_icon)
            mark.pack(side='left',padx=(0,10))
        self.label(header, '归序', 19, bold=True).pack(side='left')
        self.button(header, '操作记录 / 撤销', self.show_history).pack(side='right')
        self.result_btn=self.button(header,'查看上次结果',lambda:self.show_record_details(self.last_record))
        self.result_btn.pack(side='right',padx=(0,8))
        self.result_btn.configure(state='disabled')
        self.progress_frame=tk.Frame(self,bg=BG,padx=26)
        self.progress_text=self.label(self.progress_frame,'',9,MUTED)
        self.progress_text.pack(side='left',padx=(0,12))
        self.progress_bar=ttk.Progressbar(self.progress_frame,mode='determinate',maximum=100)
        self.progress_bar.pack(side='left',fill='x',expand=True)
        self.tabs = AnimatedTabs(self)
        self.tabs.pack(fill='both', expand=True, padx=24, pady=(18, 20))
        managed_page = tk.Frame(self.tabs, bg=BG)
        local_page = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(managed_page, text='托管归档')
        self.tabs.add(local_page, text='原位整理')
        main = tk.Frame(local_page, bg=BG)
        main.pack(fill='both', expand=True, padx=16, pady=18)
        panel_shell=RoundedPanel(main,padx=20,pady=18)
        panel_shell.pack(fill='x')
        panel=panel_shell.content
        self.label(panel, '01  选择文件夹', 11, bold=True).pack(anchor='w', pady=(0, 10))
        row = tk.Frame(panel, bg=WHITE)
        row.pack(fill='x')
        self.entry = tk.Entry(row, textvariable=self.folder, relief='flat', bg=BG, fg=INK, font=('Microsoft YaHei UI', 11))
        self.entry.pack(side='left', fill='x', expand=True, ipady=13)
        self.browse_btn = self.button(row, '浏览…', self.browse)
        self.browse_btn.pack(side='left', padx=(10, 0))
        rules = tk.Frame(panel, bg=WHITE)
        rules.pack(fill='x', pady=(16, 0))
        self.label(rules, '整理方式').grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.combo = ttk.Combobox(rules, textvariable=self.mode, values=['按文件类型', '按修改月份', '文件类型 / 修改月份'], state='readonly', width=23)
        self.combo.grid(row=1, column=0, sticky='w')
        self.label(rules, '仅整理这些扩展名（留空表示全部）', color=MUTED).grid(row=0, column=1, padx=(24, 0), sticky='w')
        self.filter_entry = tk.Entry(rules, textvariable=self.filter, relief='flat', bg=BG, fg=INK, width=32)
        self.filter_entry.grid(row=1, column=1, padx=(24, 0), sticky='ew', ipady=10)
        rules.columnconfigure(1, weight=1)
        stats = tk.Frame(main, bg=BG)
        stats.pack(fill='x', pady=18)
        self.stat_labels = []
        for heading, value in [('待整理文件', '—'), ('文件总大小', '—'), ('已跳过项目', '—')]:
            card_shell=RoundedPanel(stats,padx=18,pady=10)
            card_shell.pack(side='left', expand=True, fill='x', padx=(0, 8))
            card=card_shell.content
            self.label(card, heading, 9, MUTED).pack(anchor='w')
            label = self.label(card, value, 20, ACCENT, True)
            label.pack(anchor='w')
            self.stat_labels.append(label)
        title = tk.Frame(main, bg=BG)
        title.pack(fill='x', pady=(0, 9))
        self.label(title, '02  整理预览', 12, bold=True).pack(side='left')
        self.label(title, '仅当前层级 · 跳过子文件夹、隐藏名称和下载临时文件', 9, MUTED).pack(side='right')
        table_shell=RoundedPanel(main,padx=12,pady=12)
        table_shell.pack(fill='both', expand=True)
        table=table_shell.content
        self.tree = ttk.Treeview(table, columns=('name', 'dest', 'size'), show='headings', selectmode='extended')
        for key, title, width in [('name', '原文件', 220), ('dest', '整理后的位置', 320), ('size', '大小', 95)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=70)
        scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('even', background='#f8f9fd')
        footer = tk.Frame(main, bg=BG)
        footer.pack(fill='x', pady=(16, 0))
        self.preview_btn = self.button(footer, '生成预览', self.scan)
        self.preview_btn.pack(side='left')
        self.remove_btn = self.button(footer, '排除选中', self.exclude)
        self.remove_btn.pack(side='left', padx=8)
        self.run_btn = self.button(footer, '确认整理', self.execute, True)
        self.run_btn.pack(side='right')
        self.run_btn.configure(state='disabled')
        tk.Label(main, textvariable=self.status, bg=BG, fg=MUTED, anchor='w', wraplength=790).pack(fill='x', pady=(12, 0))
        from management_ui import Management
        self.management = Management(self, managed_page)

    def invalidate(self, *_):
        self.preview = None
        self.tree.delete(*self.tree.get_children())
        self.run_btn.configure(state='disabled')
        for label in self.stat_labels:
            label.configure(text='—')

    def browse(self):
        folder = filedialog.askdirectory(title='选择要整理的文件夹')
        if folder:
            self.folder.set(folder)
            self.scan()

    def worker(self, task, done):
        if self.busy:
            return
        self.busy = True
        self.management.set_busy(True)
        for widget in (self.preview_btn, self.run_btn, self.browse_btn, self.remove_btn, self.entry, self.filter_entry, self.combo):
            widget.configure(state='disabled')
        def run():
            try:
                self.events.put((done, task(), None))
            except Exception as exc:
                self.events.put((done, None, str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def report_progress(self,kind,completed,total,name):
        if completed==0 or completed==total or completed%max(1,total//100)==0:
            self.events.put(('progress',(kind,completed,total,name),None))

    def progress_for(self,kind):
        return lambda completed,total,name:self.report_progress(kind,completed,total,name)

    def poll(self):
        try:
            while True:
                done, result, error = self.events.get_nowait()
                if done == 'progress':
                    kind,completed,total,name=result
                    if not self.progress_frame.winfo_manager():
                        self.progress_frame.pack(fill='x',before=self.tabs)
                    self.progress_text.configure(text=f'{kind} {completed}/{total} · {name}')
                    self.progress_bar.configure(value=100*completed/max(1,total))
                    continue
                self.busy = False
                self.management.set_busy(False)
                self.progress_frame.pack_forget()
                for widget in (self.preview_btn, self.browse_btn, self.remove_btn, self.entry, self.filter_entry):
                    widget.configure(state='normal')
                self.combo.configure(state='readonly')
                if error:
                    self.invalidate()
                    self.status.set('操作未完成，请查看错误信息和操作记录。')
                    self.management.status.set('操作未完成：' + error)
                    messagebox.showerror('操作未完成', error)
                else:
                    done(result)
                self.run_btn.configure(state='normal' if self.preview and self.preview['rows'] else 'disabled')
        except queue.Empty:
            pass
        self._poll_timer=self.after(100, self.poll)

    def scan(self):
        folder = self.folder.get().strip()
        if not folder:
            self.browse()
            return
        mode = {'按文件类型': 'type', '按修改月份': 'date', '文件类型 / 修改月份': 'type_date'}[self.mode.get()]
        extensions = self.filter.get()
        self.invalidate()
        self.status.set('正在扫描文件夹…')
        self.worker(lambda: plan(folder, mode, extensions), self.render)

    def render(self, preview):
        self.preview = preview
        self.tree.delete(*self.tree.get_children())
        root = Path(preview['root'])
        for i, row in enumerate(preview['rows']):
            self.tree.insert('', 'end', iid=str(i), values=(Path(row['source']).name, str(Path(row['target']).relative_to(root)), size_text(row['size'])), tags=('even',) if i % 2 == 0 else ())
        for label, value in zip(self.stat_labels, [str(len(preview['rows'])), size_text(sum(r['size'] for r in preview['rows'])), str(preview['skipped'])]):
            label.configure(text=value)
        self.run_btn.configure(state='normal' if preview['rows'] else 'disabled')
        self.status.set('预览就绪。文件会移动到当前文件夹内的分类目录；可选中条目后排除。' if preview['rows'] else '没有符合条件的文件。可以更换文件夹或调整扩展名筛选。')

    def exclude(self):
        if self.preview and not self.busy:
            selected = {int(i) for i in self.tree.selection()}
            self.preview['rows'] = [r for i, r in enumerate(self.preview['rows']) if i not in selected]
            self.preview['skipped'] += len(selected)
            self.render(self.preview)

    def execute(self):
        if self.preview and self.preview['rows'] and not self.busy:
            preview = self.preview
            self.status.set('正在整理，请保持窗口开启…')
            self.worker(lambda: self.engine.execute(preview,self.progress_for('整理')), self.completed)

    def completed(self, record):
        self.set_last_record(record)
        self.invalidate()
        moved = sum(i['status'] == 'moved' for i in record['items'])
        errors = [f"{Path(i['source']).name}：{i['error']}" for i in record['items'] if i['status'] == 'failed']
        self.status.set(f'整理完成：成功 {moved} 个，失败 {len(errors)} 个。可在「操作记录 / 撤销」中恢复。')
        if errors:
            messagebox.showwarning('部分文件未移动', '\n'.join(errors[:12]))

    def show_history(self):
        if self.busy:
            return
        win = tk.Toplevel(self)
        win.title('操作记录')
        width = min(round(980*self.ui_scale), self.winfo_screenwidth()-100)
        height = min(round(620*self.ui_scale), self.winfo_screenheight()-120)
        win.geometry(f'{width}x{height}+60+50')
        win.minsize(min(width, round(680*self.ui_scale)), min(height, round(420*self.ui_scale)))
        win.rowconfigure(1, weight=1)
        win.columnconfigure(0, weight=1)
        win.configure(bg=BG)
        self.label(win, '操作记录', 20, bold=True).grid(row=0,column=0,sticky='w',padx=28,pady=(22,12))
        body_shell=RoundedPanel(win,padx=18,pady=16)
        body_shell.grid(row=1,column=0,sticky='nsew',padx=24)
        body=body_shell.content
        body.rowconfigure(0,weight=1)
        body.columnconfigure(0,weight=1)
        records = self.engine.history()
        tree = ttk.Treeview(body, columns=('time', 'count', 'root'), show='headings',height=4)
        for key, title, width in [('time', '整理时间', 180), ('count', '待恢复', 80), ('root', '目标文件夹', 510)]:
            tree.heading(key, text=title)
            tree.column(key, width=width)
        tree.grid(row=0,column=0,sticky='nsew')
        vbar=ttk.Scrollbar(body,orient='vertical',command=tree.yview)
        vbar.grid(row=0,column=1,sticky='ns')
        hbar=ttk.Scrollbar(body,orient='horizontal',command=tree.xview)
        hbar.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vbar.set,xscrollcommand=hbar.set)
        for i, record in enumerate(records):
            count = sum(v['status'] in {'moved', 'pending'} for v in record['items'])
            tree.insert('', 'end', iid=str(i), values=(record['time'].replace('T', ' '), count, record['root']))
        footer_shell=RoundedPanel(win,padx=18,pady=12)
        footer_shell.grid(row=2,column=0,sticky='ew',padx=24,pady=(12,18))
        footer=footer_shell.content
        self.label(footer, '选择一条记录，恢复文件原位置。', 9, MUTED).pack(side='left')
        details_btn=self.button(footer,'查看明细',lambda:self.show_record_details(records[int(tree.selection()[0])]) if tree.selection() else None)
        details_btn.pack(side='right',padx=(0,8))
        def undo():
            if self.busy or not tree.selection():
                return
            record = records[int(tree.selection()[0])]
            win.destroy()
            self.invalidate()
            self.management.invalidate()
            self.status.set('正在恢复原位置…')
            self.worker(lambda: self.engine.undo(record), self.undone)
        undo_btn=self.button(footer, '撤销选中的整理', undo, True)
        undo_btn.pack(side='right')
        undo_btn.configure(state='disabled')
        details_btn.configure(state='disabled')
        def selection_changed(_event=None):
            state='normal' if tree.selection() else 'disabled'
            undo_btn.configure(state=state)
            details_btn.configure(state=state)
        tree.bind('<<TreeviewSelect>>',selection_changed)
        tree.bind('<Double-1>',lambda e:self.show_record_details(records[int(tree.selection()[0])]) if tree.selection() else None)
        if records:
            tree.selection_set('0')
            selection_changed()
        win.history_tree=tree
        win.undo_button=undo_btn
        self.history_window=win
        from backdrop import WaveBackdrop
        win.backdrop=WaveBackdrop(win,BG)

    def set_last_record(self,record):
        self.last_record=record
        self.result_btn.configure(state='normal')

    def show_record_details(self,record):
        if not record:
            return
        win=tk.Toplevel(self)
        win.title('操作明细')
        width=min(round(1040*self.ui_scale),self.winfo_screenwidth()-80)
        height=min(round(560*self.ui_scale),self.winfo_screenheight()-100)
        win.geometry(f'{width}x{height}+80+70')
        win.configure(bg=BG)
        self.label(win,'操作明细',18,bold=True).pack(anchor='w',padx=24,pady=(20,10))
        moved=sum(i['status']=='moved' for i in record['items'])
        failed=sum(i['status']=='failed' for i in record['items'])
        undone=sum(i['status']=='undone' for i in record['items'])
        self.label(win,f'成功 {moved} · 已撤销 {undone} · 失败 {failed} · 目标 {record["root"]}',9,MUTED).pack(anchor='w',padx=24,pady=(0,10))
        shell=RoundedPanel(win,padx=14,pady=12)
        shell.pack(fill='both',expand=True,padx=24,pady=(0,20))
        body=shell.content
        tree=ttk.Treeview(body,columns=('status','source','target','error'),show='headings')
        for key,title,width in [('status','结果',90),('source','原文件',290),('target','目标文件',290),('error','原因',310)]:
            tree.heading(key,text=title)
            tree.column(key,width=width,minwidth=70)
        for item in record['items']:
            state={'moved':'已迁移','failed':'失败','undone':'已撤销','pending':'待确认','cancelled':'已取消'}.get(item['status'],item['status'])
            tree.insert('','end',values=(state,item['source'],item['target'],item.get('error','')))
        bar=ttk.Scrollbar(body,orient='vertical',command=tree.yview)
        bar.pack(side='right',fill='y')
        hbar=ttk.Scrollbar(body,orient='horizontal',command=tree.xview)
        hbar.pack(side='bottom',fill='x')
        tree.configure(yscrollcommand=bar.set,xscrollcommand=hbar.set)
        tree.pack(fill='both',expand=True)
        from backdrop import WaveBackdrop
        win.backdrop=WaveBackdrop(win,BG)

    def undone(self, result):
        count, errors = result
        if self.last_record:
            latest=next((r for r in self.engine.history() if r['id']==self.last_record['id']),None)
            if latest:
                self.set_last_record(latest)
        self.status.set(f'已恢复 {count} 个文件，{len(errors)} 个未恢复。空分类目录会保留。')
        self.management.status.set(self.status.get())
        if errors:
            messagebox.showwarning('部分文件未恢复', '\n'.join(errors[:12]))

    def close(self):
        if self.busy:
            messagebox.showinfo('正在处理', '请等待当前操作完成后再关闭。')
        else:
            self.destroy()

    def destroy(self):
        for timer in (getattr(self,'_poll_timer',None),getattr(getattr(self,'management',None),'_watch_timer',None)):
            if timer:
                try:
                    self.after_cancel(timer)
                except tk.TclError:
                    pass
        super().destroy()


def release_self_test(result_path):
    """Exercise bundled GUI resources without touching a user's files."""
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        app=App(data_dir=Path(temp)/'settings')
        app.withdraw()
        try:
            app.update()
            tkdnd=app.tk.call('package','require','tkdnd')
            assert app.logo_path.is_file()
            assert app.window_icon.width()>0
            result={'ok':True,'tkdnd':str(tkdnd),'logo':True,'title':app.title(),
                    'default_data_dir':str(default_data_dir()),
                    'portable':getattr(sys,'frozen',False) and (Path(sys.executable).parent/'便携模式.flag').is_file()}
        finally:
            app.destroy()
    Path(result_path).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        release_self_test(sys.argv[2])
    else:
        App().mainloop()
