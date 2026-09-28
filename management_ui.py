import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from managed import Registry, STANDARDS, preset, transfer_plan, import_plan, safe_name
from modern import FolderCard, RoundedPanel, GradientWave
from backdrop import WaveBackdrop
from session_state import SessionState
from watcher import WatchStore, WatchScanner

BG, WHITE, INK, MUTED = '#f5f5f7', '#ffffff', '#25272b', '#858b95'


class Management:
    def __init__(self, app, page):
        self.app = app
        self.registry = Registry(app.data_dir / 'managed.json')
        self.session_store=SessionState(app.data_dir / 'pending.json')
        remembered=self.session_store.load()
        self.watch_store=WatchStore(app.data_dir / 'watchers.json')
        self.watches=self.watch_store.load_watches()
        self.watch_scanner=WatchScanner()
        self.preview = None
        self.preview_window = None
        self.folder = None
        self.files = []
        self.paths = remembered.get('paths',[])
        self.selected_id = remembered.get('selected_id')
        self.cards = {}
        self.recursive = tk.BooleanVar(value=bool(remembered.get('recursive',False)))
        self.extensions = tk.StringVar(value=remembered.get('extensions',''))
        self.status = tk.StringVar(value='新增托管文件夹，或选中已有目标。')
        self.source = tk.StringVar(value='将外部文件或文件夹拖到上方目标卡片，也可以使用导入按钮。')
        self.controls = []
        self.page = tk.Frame(page, bg=BG, padx=16, pady=16)
        self.page.pack(fill='both', expand=True)
        top = tk.Frame(self.page, bg=BG)
        top.pack(fill='x', pady=(0, 10))
        app.label(top, '托管文件夹', 13, bold=True).pack(side='left')
        for text, command in [('自动监视', self.show_watchers), ('新增托管', lambda: self.editor()), ('编辑规则', self.edit_selected), ('取消托管', self.remove)]:
            self.btn(top, text, command).pack(side='right', padx=(8, 0))
        card_box=tk.Frame(self.page,bg=BG)
        card_box.pack(fill='x')
        self.card_canvas=tk.Canvas(card_box,bg=BG,height=round(178*app.ui_scale),highlightthickness=0)
        self.card_canvas.pack(fill='x',expand=True)
        self.card_inner=tk.Frame(self.card_canvas,bg=BG)
        self.card_canvas.create_window(0,0,anchor='nw',window=self.card_inner)
        card_scroll=ttk.Scrollbar(card_box,orient='horizontal',command=self.card_canvas.xview)
        card_scroll.pack(fill='x')
        def scroll_state(first,last):
            card_scroll.set(first,last)
            if float(first)<=0 and float(last)>=1:
                card_scroll.pack_forget()
            elif not card_scroll.winfo_manager():
                card_scroll.pack(fill='x')
        self.card_canvas.configure(xscrollcommand=scroll_state)
        self.card_inner.bind('<Configure>',lambda e:self.card_canvas.configure(scrollregion=self.card_canvas.bbox('all')))
        self.card_canvas.bind('<MouseWheel>',lambda e:self.card_canvas.xview_scroll(-int(e.delta/120),'units'))
        self.pending_shell=RoundedPanel(self.page,padx=20,pady=18)
        self.pending_shell.pack(fill='both',expand=True,pady=(12,0))
        block=self.pending_shell.content
        self.import_bar=tk.Frame(block,bg=WHITE)
        self.import_bar.pack(side='bottom',fill='x',pady=(12,0))
        import_content=self.import_bar
        row = tk.Frame(import_content, bg=WHITE)
        row.pack(fill='x')
        self.btn(row, '导入文件', self.choose_files).pack(side='left',padx=(0,8))
        self.btn(row, '导入整个文件夹', self.choose_folder).pack(side='left', padx=(0, 8))
        self.btn(row, '输入路径', self.manual_path).pack(side='left')
        def toggle_recursive():
            self.recursive.set(not self.recursive.get())
            check.configure(text=('已开启' if self.recursive.get() else '未开启')+'子文件夹')
            self.invalidate()
            self.save_session()
        check = self.app.button(row,('已开启' if self.recursive.get() else '未开启')+'子文件夹',toggle_recursive)
        check.pack(side='left', padx=16)
        self.controls.append(check)
        app.label(row, '扩展名筛选', 9, MUTED).pack(side='left')
        entry = tk.Entry(row, textvariable=self.extensions, width=17, relief='solid', bd=1)
        entry.pack(side='left', padx=8, ipady=6)
        self.controls.append(entry)
        tk.Label(import_content, textvariable=self.source, bg=WHITE, fg=MUTED, anchor='w', wraplength=1020).pack(fill='x', pady=(10, 0))
        tk.Label(import_content, textvariable=self.status, bg=WHITE, fg=MUTED, anchor='w', wraplength=1020).pack(fill='x', pady=(4, 0))
        self.extensions.trace_add('write', lambda *_: (self.invalidate(),self.save_session()))
        pending_header=tk.Frame(block,bg=WHITE)
        pending_header.pack(fill='x',pady=(4,8))
        self.pending_title=app.label(pending_header,'待分类区 · 0 项',12,bold=True)
        self.pending_title.pack(side='left')
        self.target_text=tk.StringVar(value='目标：未选择')
        tk.Label(pending_header,textvariable=self.target_text,bg=WHITE,fg='#526491',font=('Microsoft YaHei UI',9)).pack(side='left',padx=(14,0))
        self.btn(pending_header,'直接迁移',self.direct_migrate,True).pack(side='right')
        self.btn(pending_header,'查看迁移预览',self.show_preview).pack(side='right',padx=(0,8))
        self.btn(pending_header,'清空待分类',self.clear_pending).pack(side='right')
        self.btn(pending_header,'移出选中',self.remove_pending).pack(side='right',padx=8)
        self.pending=self.table(block,[('name','文件 / 文件夹',270),('kind','类型',100),('path','原位置',600)],height=5,expand=True)
        self.pending.configure(selectmode='extended')
        self.pending.bind('<<TreeviewSelect>>',lambda e:self.invalidate() if not self.app.busy else None)
        self.pending.bind('<Button-1>',lambda e:'break' if self.app.busy else None)
        self.pending.bind('<KeyPress>',lambda e:'break' if self.app.busy else None)
        for widget in (self.pending,self.pending_title):
            widget.drop_target_register('DND_Files')
            widget.dnd_bind('<<DropEnter>>',lambda e:'refuse_drop' if self.app.busy else 'copy')
            widget.dnd_bind('<<Drop>>',self.drop_pending)
        self.source.set('拖入待分类区暂存；选择目标后可直接迁移，或先查看预览。')
        self.preview_window = None
        self.summary = app.label(self.page, '', 1, bg=BG)
        self.items = None
        self.execute_btn = None
        self.refresh()
        self.refresh_pending()
        self._watch_timer=self.app.after(5000,self.watch_tick)

    def save_session(self):
        try:
            self.session_store.save({'paths':self.paths,'selected_id':self.selected_id,'recursive':self.recursive.get(),'extensions':self.extensions.get()})
        except OSError as exc:
            self.status.set('待分类区保存失败：'+str(exc))

    def btn(self, parent, text, command, primary=False):
        button = self.app.button(parent, text, command, primary)
        self.controls.append(button)
        return button

    def table(self, parent, columns, height=6, expand=False):
        shell=RoundedPanel(parent,padx=12,pady=12)
        shell.pack(fill='both' if expand else 'x', expand=expand)
        box=shell.content
        tree = ttk.Treeview(box, columns=[c[0] for c in columns], show='headings', height=height, selectmode='browse')
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=70)
        vbar = ttk.Scrollbar(box, orient='vertical', command=tree.yview)
        hbar = ttk.Scrollbar(box, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side='right', fill='y')
        hbar.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True)
        return tree

    def set_busy(self, busy):
        for control in self.controls:
            control.configure(state='disabled' if busy else 'normal')
        if self.execute_btn is not None:
            self.execute_btn.configure(state='normal' if not busy and self.preview and self.preview['rows'] else 'disabled')

    def refresh(self, select=None):
        for child in self.card_inner.winfo_children():
            if not getattr(child,'_wave_layer',False):
                child.destroy()
        self.cards={}
        for i,p in enumerate(self.registry.profiles):
            card=FolderCard(self.card_inner,p,i,self.select_target,self.receive_drop,lambda:self.app.busy,self.app.ui_scale)
            card.pack(side='left',padx=(0,14),pady=8)
            self.cards[p['id']]=card
            card.bind('<Double-1>',lambda e:self.edit_selected())
        self.add_card=FolderCard(self.card_inner,{'id':'__add__','name':'新增托管'},len(self.cards),lambda _:self.editor(),lambda _id,paths:self.create_from_drop(paths),lambda:self.app.busy,self.app.ui_scale,is_add=True)
        self.add_card.pack(side='left',padx=(0,14),pady=8)
        for target in (self.card_canvas,self.card_inner):
            target.drop_target_register('DND_Files')
            target.dnd_bind('<<DropEnter>>',lambda e:'refuse_drop' if self.app.busy else 'copy')
            target.dnd_bind('<<Drop>>',self.drop_new_target)
        self.selected_id = select if select in self.cards else (self.selected_id if self.selected_id in self.cards else next(iter(self.cards),None))
        for key,card in self.cards.items():
            card.selected=key==self.selected_id
            card.draw()
        self.invalidate()
        self.save_session()

    def selected(self):
        return next((p for p in self.registry.profiles if p['id']==self.selected_id),None)

    def select_target(self, profile_id):
        if self.app.busy:
            return
        self.selected_id=profile_id
        for key,card in self.cards.items():
            card.selected=key==profile_id
            card.draw()
        self.invalidate()
        self.save_session()

    def invalidate(self):
        self.preview = None
        if self.items is not None:
            self.items.delete(*self.items.get_children())
        if self.execute_btn is not None:
            self.execute_btn.configure(state='disabled')
        profile=self.selected()
        self.target_text.set('目标：'+profile['name'] if profile else '目标：未选择')
        self.status.set('归档目标：'+profile['name'] if profile else '请先新增托管文件夹。')

    def edit_selected(self):
        if not self.app.busy and self.selected():
            self.editor(self.selected())

    def remove(self):
        p = self.selected()
        if not self.app.busy and p:
            try:
                self.registry.remove(p['id'])
                self.watches=[w for w in self.watches if w['profile_id']!=p['id']]
                self.watch_store.save_watches(self.watches)
                self.refresh()
                self.status.set('已取消托管，文件夹及其中的文件均已保留。')
            except OSError as exc:
                messagebox.showerror('保存失败', str(exc))

    def choose_folder(self):
        if self.app.busy:
            return
        path = filedialog.askdirectory(title='选择要迁移的来源文件夹')
        if path:
            self.accept_paths([path])

    def choose_files(self):
        if self.app.busy:
            return
        paths = filedialog.askopenfilenames(title='选择要归档的文件（支持多选）')
        if paths:
            self.accept_paths(list(paths))

    def manual_path(self):
        if self.app.busy:
            return
        value=simpledialog.askstring('输入文件或文件夹路径','输入完整路径：',parent=self.app)
        if value:
            self.accept_paths([value.strip().strip('"')])

    def receive_drop(self, profile_id, paths):
        if self.app.busy:
            return
        self.select_target(profile_id)
        self.accept_paths(paths,auto_preview=True)

    def create_from_drop(self, paths):
        if self.app.busy:
            return
        try:
            if len(paths)!=1:
                raise ValueError('请一次拖入一个已有文件夹。')
            path=Path(paths[0]).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise ValueError('新增托管请拖入文件夹。文件可拖到已有托管卡片。')
            profile={'id':uuid.uuid4().hex,'name':path.name,'path':str(path),'standard':'文件类型','rules':preset('文件类型'),'fallback':'其他文件'}
            saved=self.registry.save(profile)
            self.refresh(saved['id'])
            self.status.set('已托管 '+path.name+'，可在「编辑规则」中调整分类。')
        except (OSError,ValueError) as exc:
            self.status.set(str(exc))

    def drop_new_target(self,event):
        if self.app.busy:
            return 'refuse_drop'
        self.create_from_drop(list(self.app.tk.splitlist(event.data)))
        return 'copy'

    def accept_paths(self, paths, auto_preview=False):
        if self.app.busy:
            return
        incoming=[]
        for raw in paths:
            path=str(Path(raw).expanduser().absolute())
            if path.casefold() not in {p.casefold() for p in self.paths}:
                self.paths.append(path)
            incoming.append(path.casefold())
        self.folder,self.files=None,[]
        self.refresh_pending(incoming)
        self.invalidate()
        self.save_session()
        if auto_preview:
            self.app.after_idle(self.scan)

    def refresh_pending(self, selected=()):
        self.pending.delete(*self.pending.get_children())
        ids=[]
        for i,raw in enumerate(self.paths):
            path=Path(raw)
            kind='文件夹' if path.is_dir() else ('文件' if path.exists() else '不存在')
            self.pending.insert('','end',iid=str(i),values=(path.name,kind,str(path)))
            if raw.casefold() in selected:
                ids.append(str(i))
        if ids:
            self.pending.selection_set(ids)
        self.pending_title.configure(text=f'待分类区 · {len(self.paths)} 项')
        self.source.set('可继续批量拖入；选中部分条目进行分类，未选中时处理全部。')

    def drop_pending(self,event):
        if self.app.busy:
            return 'refuse_drop'
        self.accept_paths(list(self.app.tk.splitlist(event.data)))
        return 'copy'

    def remove_pending(self):
        if self.app.busy:
            return
        selected={int(i) for i in self.pending.selection()}
        self.paths=[p for i,p in enumerate(self.paths) if i not in selected]
        self.refresh_pending()
        self.invalidate()
        self.save_session()

    def clear_pending(self):
        if self.app.busy:
            return
        self.paths=[]
        self.folder,self.files=None,[]
        self.refresh_pending()
        self.invalidate()
        self.save_session()

    def scan(self):
        if self.app.busy:
            return
        profile = self.selected()
        if not profile or not (self.paths or self.folder or self.files):
            self.status.set('请先选中目标卡片，再拖入文件，或点击导入按钮。')
            return
        selection=[int(i) for i in self.pending.selection()]
        paths=([self.paths[i] for i in selection] if selection else list(self.paths)) or ([self.folder] if self.folder else list(self.files))
        recursive, extensions = self.recursive.get(), self.extensions.get()
        self.invalidate()
        self.status.set('正在生成预览…')
        self.app.worker(lambda: import_plan(profile, paths, recursive, extensions), self.render)

    def direct_migrate(self):
        if self.app.busy:
            return
        profile=self.selected()
        if not profile or not self.paths:
            self.status.set('请先选择托管目标并加入待分类文件。')
            return
        selection=[int(i) for i in self.pending.selection()]
        paths=[self.paths[i] for i in selection] if selection else list(self.paths)
        if (len(paths)>1 or any(Path(p).is_dir() for p in paths)) and not messagebox.askyesno('确认直接迁移',f'将所选内容直接分类到「{profile["name"]}」？\n{profile["path"]}',parent=self.app):
            return
        recursive,extensions=self.recursive.get(),self.extensions.get()
        self.invalidate()
        self.status.set('正在分类并迁移…')
        def task():
            plan=import_plan(profile,paths,recursive,extensions)
            return self.app.engine.execute(plan,self.app.progress_for('迁移')) if plan['rows'] else None
        self.app.worker(task,self.direct_completed)

    def direct_completed(self,record):
        if record is None:
            self.status.set('没有符合当前规则的文件可迁移。')
        else:
            self.completed(record)

    def show_preview(self):
        if self.app.busy:
            return
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.deiconify()
            self.preview_window.lift()
            if self.preview is None:
                self.scan()
            return
        win = tk.Toplevel(self.app)
        self.preview_window = win
        win.title('迁移预览')
        width = min(round(980*self.app.ui_scale), self.app.winfo_screenwidth()-100)
        height = min(round(600*self.app.ui_scale), self.app.winfo_screenheight()-120)
        win.geometry(f'{width}x{height}+70+70')
        win.configure(bg=BG)
        def close_preview():
            win.withdraw()
        win.protocol('WM_DELETE_WINDOW', close_preview)
        self.app.label(win, '迁移预览', 18, bold=True).pack(anchor='w', padx=22, pady=(18, 4))
        self.summary = self.app.label(win, '尚未生成预览', 10, MUTED)
        self.summary.pack(anchor='w', padx=22, pady=(0, 10))
        self.items = self.table(win, [('source', '原文件位置', 500), ('target', '目标内位置', 360), ('size', '大小', 100)], height=12, expand=True)
        self.items.configure(selectmode='extended')
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill='x', padx=22, pady=16)
        self.app.button(footer, '重新生成', self.scan).pack(side='left')
        self.app.button(footer, '排除选中', self.exclude).pack(side='left', padx=8)
        self.execute_btn = self.app.button(footer, '确认迁移', self.execute, True)
        self.execute_btn.pack(side='right')
        self.execute_btn.configure(state='normal' if self.preview and self.preview['rows'] else 'disabled')
        if self.preview:
            self.render(self.preview)
        else:
            self.scan()

    def render(self, preview):
        from app import size_text
        self.preview = preview
        if self.items is None:
            return
        self.items.delete(*self.items.get_children())
        for i, row in enumerate(preview['rows']):
            self.items.insert('', 'end', iid=str(i), values=(row['source'], str(Path(row['target']).relative_to(preview['root'])), size_text(row['size'])))
        self.summary.configure(text=f"{len(preview['rows'])} 个文件 · {size_text(sum(r['size'] for r in preview['rows']))} · 跳过 {preview['skipped']} 项")
        self.status.set('目标：' + preview['root'])
        self.execute_btn.configure(state='normal' if preview['rows'] else 'disabled')

    def exclude(self):
        if self.preview and self.items is not None and not self.app.busy:
            ids = {int(i) for i in self.items.selection()}
            self.preview['rows'] = [r for i, r in enumerate(self.preview['rows']) if i not in ids]
            self.preview['skipped'] += len(ids)
            self.render(self.preview)

    def execute(self):
        if self.app.busy or not self.preview or not self.preview['rows']:
            return
        preview = self.preview
        self.status.set('正在迁移…')
        self.app.worker(lambda: self.app.engine.execute(preview,self.app.progress_for('迁移')), self.completed)

    def completed(self, record):
        self.app.set_last_record(record)
        moved_paths={r['source'].casefold() for r in record['items'] if r['status']=='moved'}
        self.paths=[p for p in self.paths if p.casefold() not in moved_paths]
        self.refresh_pending()
        self.save_session()
        self.app.invalidate()
        self.invalidate()
        moved = sum(r['status'] == 'moved' for r in record['items'])
        errors = [Path(r['source']).name + '：' + r['error'] for r in record['items'] if r['status'] == 'failed']
        self.status.set(f'已迁移 {moved} 个文件，失败 {len(errors)} 个。可从操作记录撤销。')
        if errors:
            messagebox.showwarning('部分文件未迁移', '\n'.join(errors[:15]))

    def editor(self, profile=None):
        if self.app.busy:
            return
        ProfileEditor(self, profile)

    def show_watchers(self):
        if self.app.busy:
            return
        profile_at_open=self.selected()
        win=tk.Toplevel(self.app)
        win.title('自动监视')
        width=min(round(880*self.app.ui_scale),self.app.winfo_screenwidth()-100)
        height=min(round(500*self.app.ui_scale),self.app.winfo_screenheight()-120)
        win.geometry(f'{width}x{height}+70+60')
        win.configure(bg=BG)
        self.app.label(win,'自动监视来源文件夹',18,bold=True).pack(anchor='w',padx=24,pady=(20,8))
        self.app.label(win,'当前托管目标：'+(profile_at_open['name'] if profile_at_open else '请先选择托管目标'),10).pack(anchor='w',padx=24,pady=(0,6))
        self.app.label(win,'软件运行期间，来源中的文件保持稳定后会自动归档。包含启用时已有文件，仅监视当前层级。',9,MUTED).pack(anchor='w',padx=24,pady=(0,12))
        shell=RoundedPanel(win,padx=14,pady=12)
        shell.pack(fill='both',expand=True,padx=24)
        box=shell.content
        tree=ttk.Treeview(box,columns=('state','source','target'),show='headings')
        for key,title,size in [('state','状态',90),('source','来源文件夹',430),('target','托管目标',220)]:
            tree.heading(key,text=title)
            tree.column(key,width=size,minwidth=70)
        tree.pack(fill='both',expand=True)
        win.watch_tree=tree
        def redraw():
            tree.delete(*tree.get_children())
            profiles={p['id']:p for p in self.registry.profiles}
            for i,watch in enumerate(self.watches):
                tree.insert('','end',iid=str(i),values=('运行中' if watch.get('enabled') else '已暂停',watch['source'],profiles.get(watch['profile_id'],{}).get('name','目标不存在')))
        def add():
            profile=profile_at_open
            if not profile:
                messagebox.showinfo('选择目标','请先在主界面选中一个托管目标。',parent=win)
                return
            chosen=filedialog.askdirectory(parent=win,title='选择需要自动监视的来源文件夹')
            if not chosen:
                return
            try:
                source=Path(chosen).resolve(strict=True)
                target=Path(profile['path']).resolve(strict=True)
            except OSError as exc:
                messagebox.showerror('无法监视',str(exc),parent=win)
                return
            if source==target or source.is_relative_to(target) or target.is_relative_to(source):
                messagebox.showerror('无法监视','来源与托管目标不能相同或互相包含。',parent=win)
                return
            if any(Path(w['source'])==source and w['profile_id']==profile['id'] for w in self.watches):
                messagebox.showinfo('已添加','这个来源和目标已在列表中。',parent=win)
                return
            self.watches.append({'id':uuid.uuid4().hex,'source':str(source),'profile_id':profile['id'],'enabled':True})
            self.watch_store.save_watches(self.watches)
            redraw()
            self.status.set('已监视 '+source.name+'；软件运行期间会自动归档新文件。')
        def toggle():
            if tree.selection():
                watch=self.watches[int(tree.selection()[0])]
                watch['enabled']=not watch.get('enabled',False)
                self.watch_store.save_watches(self.watches)
                redraw()
        def remove():
            if tree.selection():
                self.watches.pop(int(tree.selection()[0]))
                self.watch_store.save_watches(self.watches)
                redraw()
        footer=RoundedPanel(win,padx=14,pady=10)
        footer.pack(fill='x',padx=24,pady=(12,20))
        self.app.button(footer.content,'添加来源文件夹',add,True).pack(side='left')
        self.app.button(footer.content,'暂停 / 启用',toggle).pack(side='left',padx=8)
        self.app.button(footer.content,'移除',remove).pack(side='left')
        redraw()
        win.backdrop=WaveBackdrop(win,BG)

    def watch_tick(self):
        try:
            if not self.app.busy and self.watches:
                available=[w for w in self.watches if any(p['id']==w['profile_id'] for p in self.registry.profiles)]
                ready=self.watch_scanner.ready(available)
                if ready:
                    watch,paths=ready
                    profile=next(p for p in self.registry.profiles if p['id']==watch['profile_id'])
                    source_root=Path(watch['source']).resolve()
                    target_root=Path(profile['path']).resolve()
                    if source_root==target_root or source_root.is_relative_to(target_root) or target_root.is_relative_to(source_root):
                        self.status.set('监视来源与目标发生重叠，已跳过：'+watch['source'])
                        return
                    self.watch_scanner.mark_attempted(watch,paths)
                    self.status.set(f'自动归档 {len(paths)} 个文件到「{profile["name"]}」…')
                    def task():
                        preview=import_plan(profile,paths)
                        return self.app.engine.execute(preview,self.app.progress_for('自动归档')) if preview['rows'] else None
                    self.app.worker(task,lambda record:self.completed(record) if record else None)
        finally:
            if self.app.winfo_exists():
                self._watch_timer=self.app.after(5000,self.watch_tick)


class ProfileEditor(tk.Toplevel):
    def __init__(self, manager, profile=None):
        super().__init__(manager.app)
        self.manager, self.app = manager, manager.app
        self.profile_id = profile['id'] if profile else uuid.uuid4().hex
        self.title('编辑托管文件夹' if profile else '新增托管文件夹')
        self.compact_size=(min(round(740*self.app.ui_scale),self.winfo_screenwidth()-100),min(round(390*self.app.ui_scale),self.winfo_screenheight()-120))
        self.expanded_size=(min(round(940*self.app.ui_scale),self.winfo_screenwidth()-100),min(round(780*self.app.ui_scale),self.winfo_screenheight()-120))
        self.geometry(f'{self.compact_size[0]}x{self.compact_size[1]}+60+50')
        self.minsize(min(round(620*self.app.ui_scale),self.compact_size[0]),min(round(350*self.app.ui_scale),self.compact_size[1]))
        self.configure(bg=BG)
        self.transient(self.app)
        self.name = tk.StringVar(value=profile['name'] if profile else '')
        self.path = tk.StringVar(value=profile['path'] if profile else '')
        self.standard = tk.StringVar(value=profile['standard'] if profile else STANDARDS[0])
        self.fallback = tk.StringVar(value=profile['fallback'] if profile else '其他文件')
        self.rule_name, self.rule_match = tk.StringVar(), tk.StringVar()
        self.prefix = tk.StringVar(value='分类')
        self.quantity = tk.StringVar(value='3')
        self.count = tk.StringVar()
        shell=RoundedPanel(self,padx=24,pady=20)
        shell.pack(fill='both',expand=True,padx=22,pady=22)
        main=shell.content
        self.app.label(main,'新增托管' if not profile else '编辑托管',18,bold=True).pack(anchor='w',pady=(0,12))
        self.folder_drop_hint=tk.StringVar(value='将已有文件夹拖到这里')
        self.folder_drop_zone=tk.Label(main,textvariable=self.folder_drop_hint,bg='#eef2ff',fg='#526491',padx=20,pady=20,anchor='center',font=('Microsoft YaHei UI',12))
        self.folder_drop_zone.pack(fill='x',pady=(0,12))
        self.register_folder_drop(self.folder_drop_zone)
        self.app.button(main,'选择已有文件夹',self.existing,True).pack(anchor='w',pady=(0,16))
        for label, var in [('显示名称', self.name), ('文件夹完整路径', self.path)]:
            row = tk.Frame(main, bg=WHITE)
            row.pack(fill='x', pady=(0, 8))
            self.app.label(row, label, 10).pack(side='left', padx=(0, 12))
            entry=tk.Entry(row, textvariable=var, relief='flat', bg='#f4f5f8', bd=0)
            entry.pack(side='left', fill='x', expand=True, ipady=8)
            self.register_folder_drop(entry)
        toggle=self.app.button(main,'高级选项  ▾',self.toggle_advanced)
        toggle.pack(anchor='w',pady=(2,8))
        self.advanced_toggle=toggle
        self.advanced=tk.Frame(main,bg=WHITE)
        self.advanced_canvas=tk.Canvas(self.advanced,bg=WHITE,highlightthickness=0,bd=0)
        advanced_scroll=ttk.Scrollbar(self.advanced,orient='vertical',command=self.advanced_canvas.yview)
        advanced_scroll.pack(side='right',fill='y')
        self.advanced_canvas.pack(side='left',fill='both',expand=True)
        self.advanced_canvas.configure(yscrollcommand=advanced_scroll.set)
        advanced=tk.Frame(self.advanced_canvas,bg=WHITE)
        advanced_window=self.advanced_canvas.create_window(0,0,anchor='nw',window=advanced)
        advanced.bind('<Configure>',lambda e:self.advanced_canvas.configure(scrollregion=self.advanced_canvas.bbox('all')))
        self.advanced_canvas.bind('<Configure>',lambda e:self.advanced_canvas.itemconfigure(advanced_window,width=e.width))
        self.advanced_canvas.bind('<MouseWheel>',lambda e:self.advanced_canvas.yview_scroll(-int(e.delta/120),'units'))
        self.app.button(advanced,'新建空文件夹',self.new_folder).pack(anchor='w',pady=(0,8))
        row = tk.Frame(advanced, bg=WHITE)
        row.pack(fill='x', pady=(2, 8))
        self.app.label(row, '分类标准').pack(side='left', padx=(0, 12))
        ttk.Combobox(row, textvariable=self.standard, values=STANDARDS, state='readonly', width=16).pack(side='left')
        self.app.button(row, '载入示例规则', self.load_preset).pack(side='left', padx=10)
        self.hint = self.app.label(advanced, '', 9, MUTED)
        self.hint.pack(anchor='w', pady=(0, 8))
        self.standard.trace_add('write', lambda *_: self.update_hint())
        self.rules = manager.table(advanced, [('name', '子文件夹名称', 240), ('match', '匹配内容（逗号分隔）', 570)], height=4, expand=False)
        self.rules.bind('<<TreeviewSelect>>', self.select_rule)
        form = tk.Frame(advanced, bg=WHITE)
        form.pack(fill='x', pady=10)
        tk.Entry(form, textvariable=self.rule_name, width=20, relief='solid', bd=1).pack(side='left', ipady=9)
        tk.Entry(form, textvariable=self.rule_match, relief='solid', bd=1).pack(side='left', fill='x', expand=True, padx=8, ipady=9)
        self.app.button(form, '添加', self.add_rule).pack(side='left')
        self.app.button(form, '更新选中', self.update_rule).pack(side='left', padx=(8, 0))
        actions = tk.Frame(advanced, bg=WHITE)
        actions.pack(fill='x')
        for text, command in [('删除选中', self.delete_rule), ('上移', lambda: self.shift(-1)), ('下移', lambda: self.shift(1))]:
            self.app.button(actions, text, command).pack(side='left', padx=(0, 8))
        tk.Label(actions, textvariable=self.count, bg=WHITE, fg=MUTED).pack(side='right')
        bulk = tk.Frame(advanced, bg=WHITE)
        bulk.pack(fill='x', pady=10)
        self.app.label(bulk, '批量创建名称').pack(side='left', padx=(0, 10))
        tk.Entry(bulk, textvariable=self.prefix, width=14).pack(side='left', ipady=7)
        def change_quantity(delta):
            try:
                self.quantity.set(str(max(1,min(200,int(self.quantity.get())+delta))))
            except ValueError:
                self.quantity.set('1')
        self.app.button(bulk,'−',lambda:change_quantity(-1)).pack(side='left',padx=(8,0))
        tk.Entry(bulk,textvariable=self.quantity,width=4,justify='center',relief='flat').pack(side='left',padx=6,ipady=7)
        self.app.button(bulk,'+',lambda:change_quantity(1)).pack(side='left',padx=(0,8))
        self.app.button(bulk, '添加编号子文件夹', self.bulk).pack(side='left')
        foot = tk.Frame(advanced, bg=WHITE)
        foot.pack(fill='x', pady=(0, 10))
        self.app.label(foot, '未匹配文件放入').pack(side='left', padx=(0, 10))
        tk.Entry(foot, textvariable=self.fallback, width=24).pack(side='left', ipady=8)
        self.app.label(advanced, '规则从上到下匹配；空规则仅创建目录。修改规则不移动已归档文件。', 9, MUTED).pack(anchor='w')
        bottom = tk.Frame(main, bg=WHITE)
        bottom.pack(side='bottom',fill='x', pady=(12, 0))
        self.bottom=bottom
        self.app.button(bottom, '保存并创建目录', self.save, True).pack(side='right')
        self.app.button(bottom, '取消', self.destroy).pack(side='right', padx=10)
        self.fill(profile['rules'] if profile else preset(self.standard.get()))
        self.update_hint()
        self.backdrop=WaveBackdrop(self,BG)
        self.grab_set()

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.pack_forget()
            self.advanced_toggle.configure(text='高级选项  ▾')
            width,height=self.compact_size
        else:
            self.advanced.pack(fill='both',expand=True)
            self.advanced_toggle.configure(text='收起高级选项  ▴')
            width,height=self.expanded_size
        self.geometry(f'{width}x{height}')

    def update_hint(self):
        hints = {'文件类型': '匹配扩展名，如 pdf,docx；子文件夹名称可以自行修改。', '扩展名': '匹配扩展名，如 jpg,png；同一目录可接收多个扩展名。', '文件名关键词': '文件名包含任一关键词即命中，例如 合同,协议。', '修改月份': '匹配文件修改月份，例如 2026-09,2026-10。'}
        self.hint.configure(text=hints[self.standard.get()])

    def existing(self):
        path = filedialog.askdirectory(parent=self, title='选择要托管的文件夹')
        if path:
            try:
                self.use_existing_folder(path)
            except (ValueError,OSError) as exc:
                self.folder_drop_hint.set(str(exc))

    def register_folder_drop(self,widget):
        widget.drop_target_register('DND_Files')
        widget.dnd_bind('<<DropEnter>>',self.folder_drag_enter)
        widget.dnd_bind('<<DropLeave>>',lambda e:self.folder_drop_zone.configure(bg='#e9eefb'))
        widget.dnd_bind('<<Drop>>',self.drop_existing_folder)

    def folder_drag_enter(self,event):
        self.folder_drop_zone.configure(bg='#d7e2ff')
        return 'copy'

    def use_existing_folder(self,raw):
        path=Path(raw).expanduser()
        if not path.is_dir():
            raise ValueError('请拖入已有文件夹，不能拖入单个文件。')
        path=path.resolve(strict=True)
        if any(p['id']!=self.profile_id and Path(p['path']).resolve()==path for p in self.manager.registry.profiles):
            raise ValueError('这个文件夹已经被托管，请在主界面编辑其规则。')
        old_path=self.path.get()
        if not self.name.get().strip() or (old_path and self.name.get()==Path(old_path).name):
            self.name.set(path.name or str(path))
        self.path.set(str(path))
        self.folder_drop_hint.set('已选择文件夹；设置分类规则后点击「保存并创建目录」。')

    def drop_existing_folder(self,event):
        self.folder_drop_zone.configure(bg='#e9eefb')
        try:
            paths=self.tk.splitlist(event.data)
            if len(paths)!=1:
                raise ValueError('每次创建一个托管目标，请只拖入一个文件夹。')
            self.use_existing_folder(paths[0])
            return 'copy'
        except (ValueError,OSError,tk.TclError) as exc:
            self.folder_drop_hint.set(str(exc))
            return 'refuse_drop'

    def new_folder(self):
        parent = filedialog.askdirectory(parent=self, title='选择新文件夹的保存位置')
        if not parent:
            return
        name = simpledialog.askstring('新建文件夹', '文件夹名称', parent=self)
        if name:
            try:
                safe_name(name)
                self.path.set(str(Path(parent) / name))
                self.name.set(name)
            except ValueError as exc:
                messagebox.showerror('名称无效', str(exc), parent=self)

    def fill(self, rows):
        self.rules.delete(*self.rules.get_children())
        for row in rows:
            self.rules.insert('', 'end', values=(row['name'], row['match']))
        self.update_count()

    def update_count(self):
        self.count.set(f'{len(self.rules.get_children())} 个分类目录 + 1 个未匹配目录')

    def load_preset(self):
        self.fill(preset(self.standard.get()))

    def select_rule(self, *_):
        ids = self.rules.selection()
        if ids:
            values = self.rules.item(ids[0], 'values')
            self.rule_name.set(values[0])
            self.rule_match.set(values[1])

    def valid_rule(self):
        try:
            safe_name(self.rule_name.get().strip())
            return True
        except ValueError as exc:
            messagebox.showerror('名称无效', str(exc), parent=self)
            return False

    def add_rule(self):
        if self.valid_rule():
            self.rules.insert('', 'end', values=(self.rule_name.get().strip(), self.rule_match.get()))
            self.update_count()

    def update_rule(self):
        ids = self.rules.selection()
        if ids and self.valid_rule():
            self.rules.item(ids[0], values=(self.rule_name.get().strip(), self.rule_match.get()))

    def delete_rule(self):
        self.rules.delete(*self.rules.selection())
        self.update_count()

    def shift(self, delta):
        ids = self.rules.selection()
        if ids:
            self.rules.move(ids[0], '', max(0, self.rules.index(ids[0]) + delta))

    def bulk(self):
        try:
            quantity = int(self.quantity.get())
            if not 1 <= quantity <= 200:
                raise ValueError('数量应为 1 到 200。')
            prefix = safe_name(self.prefix.get().strip())
            names = {self.rules.item(i, 'values')[0].casefold() for i in self.rules.get_children()}
            number = 1
            for _ in range(quantity):
                while f'{prefix}{number:02}'.casefold() in names:
                    number += 1
                name = f'{prefix}{number:02}'
                self.rules.insert('', 'end', values=(name, ''))
                names.add(name.casefold())
            self.update_count()
        except ValueError as exc:
            messagebox.showerror('无法添加', str(exc), parent=self)

    def save(self):
        try:
            if not self.path.get().strip() or not self.name.get().strip():
                raise ValueError('请填写显示名称与文件夹路径。')
            if not Path(self.path.get().strip()).is_absolute():
                raise ValueError('请使用完整的绝对路径。')
            rows = [dict(zip(('name', 'match'), self.rules.item(i, 'values'))) for i in self.rules.get_children()]
            profile = {'id': self.profile_id, 'name': self.name.get().strip(), 'path': self.path.get().strip(), 'standard': self.standard.get(), 'rules': rows, 'fallback': self.fallback.get().strip()}
            self.manager.registry.save(profile)
            self.manager.refresh(profile['id'])
            self.manager.status.set('托管配置已保存，子文件夹已创建。')
            self.destroy()
        except (OSError, ValueError) as exc:
            messagebox.showerror('保存失败', str(exc), parent=self)
