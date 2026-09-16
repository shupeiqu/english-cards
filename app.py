import random
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from core import Store, DATA_DIR
from collect import launch_worker

class App:
    def __init__(self, root, store):
        self.root, self.store = root, store
        self.editing = None
        self.revealed = False
        self._speech = None
        self.study_count = tk.StringVar(master=root, value='20')
        root.title('英语卡片 · 划词收藏版')
        root.geometry(f'1000x{min(780, max(640, root.winfo_screenheight()-100))}')
        root.minsize(880, 640)
        root.configure(bg='#f4f5f7')
        style = ttk.Style()
        style.configure('Treeview', rowheight=34, font=('Arial', 13))
        style.configure('Treeview.Heading', font=('Arial', 13, 'bold'))
        style.configure('TButton', padding=8)
        header = tk.Frame(root, bg='#f4f5f7', padx=26, pady=18)
        header.pack(fill='x')
        tk.Label(header, text='英语卡片', font=('Arial', 25, 'bold'), bg='#f4f5f7', fg='#183c39').pack(anchor='w')
        tk.Label(header, text='选中英文 → 右键「服务」→「收藏到英语卡片」· 中文自动翻译保存', font=('Arial', 13), bg='#f4f5f7', fg='#667574').pack(anchor='w', pady=(5,0))
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill='both', expand=True, padx=24, pady=(0,24))
        self.library = ttk.Frame(self.tabs, padding=18)
        self.study = ttk.Frame(self.tabs, padding=22)
        self.tabs.add(self.library, text='  我的收藏  ')
        self.tabs.add(self.study, text='  学习卡片  ')
        self.build_library()
        self.build_study()
        self.refresh()
        self.render_card()
        self.worker = None
        self.signature = None
        self.current_id = self.store.queue[0] if self.store.queue else None
        self._last_tab = self.tabs.select()
        self.tabs.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        root.after(800, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)
    def build_library(self):
        # Reserve space for all controls; only the scrollable list absorbs resizing.
        self.library.columnconfigure(0, weight=1)
        self.library.rowconfigure(4, weight=1, minsize=60)
        form = ttk.Frame(self.library)
        form.grid(row=0, column=0, sticky='ew')
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text='英文 · 单词、短语或句子').grid(row=0,column=0,sticky='w')
        ttk.Label(form, text='中文释义 · 留空自动翻译').grid(row=0,column=1,sticky='w',padx=(12,0))
        self.en = tk.Text(form, height=3, font=('Arial',14), wrap='word', undo=True)
        self.zh = tk.Text(form, height=3, font=('Arial',14), wrap='word', undo=True)
        self.en.grid(row=1,column=0,sticky='ew',pady=7)
        self.zh.grid(row=1,column=1,sticky='ew',padx=(12,0),pady=7)
        actions = ttk.Frame(self.library)
        actions.grid(row=1, column=0, sticky='ew', pady=(0,8))
        ttk.Button(actions,text='如何划词收藏',command=self.capture_help).pack(side='left')
        self.save_button = ttk.Button(actions,text='加入收藏',command=self.add)
        self.save_button.pack(side='left',padx=8)
        ttk.Button(actions,text='清空 / 取消编辑',command=self.clear).pack(side='left')
        ttk.Label(self.library, text='自动翻译：MyMemory · 只发送你收藏的英文 · 需联网，每日免费额度有限。').grid(row=2, column=0, sticky='w', pady=(0,8))
        self.search = tk.StringVar()
        searchrow = ttk.Frame(self.library)
        searchrow.grid(row=3, column=0, sticky='ew', pady=(0,8))
        ttk.Label(searchrow,text='搜索收藏  ').pack(side='left')
        ttk.Entry(searchrow,textvariable=self.search).pack(side='left',fill='x',expand=True)
        self.search.trace_add('write',lambda *_:self.refresh())
        table = ttk.Frame(self.library)
        table.grid(row=4, column=0, sticky='nsew')
        self.tree = ttk.Treeview(table,columns=('en','zh','status'),show='headings',selectmode='extended',height=4)
        self.tree.heading('en',text='英文')
        self.tree.heading('zh',text='中文释义 · 留空自动翻译')
        self.tree.heading('status',text='翻译状态')
        self.tree.column('status',width=100,stretch=False)
        self.tree.column('en',width=330)
        self.tree.column('zh',width=340)
        scroll = ttk.Scrollbar(table,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        self.tree.bind('<Double-1>',lambda e:self.edit())
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.update_count())
        row = ttk.Frame(self.library)
        row.grid(row=5, column=0, sticky='ew', pady=8)
        ttk.Button(row,text='编辑选中项',command=self.edit).pack(side='left')
        ttk.Button(row,text='删除选中项',command=self.delete).pack(side='left',padx=8)
        ttk.Button(row,text='重试翻译',command=self.retry_translation).pack(side='left')
        self.count = ttk.Label(row)
        self.count.pack(side='right')
        self.detail = ttk.Label(self.library,text='按住 ⌘ / Shift 多选。双击词条可修改释义。仅翻译完成的词条参与学习。',wraplength=840)
        self.detail.grid(row=6, column=0, sticky='w')
        row = ttk.Frame(self.library)
        row.grid(row=7, column=0, sticky='ew', pady=(8,0))
        ttk.Label(row,text='每轮 ').pack(side='left')
        self.count_input = ttk.Spinbox(row,from_=1,to=99999,width=5,textvariable=self.study_count)
        self.count_input.pack(side='left')
        ttk.Label(row,text=' 条  ').pack(side='left')
        self.random_button = ttk.Button(row,text='随机开始学习',command=self.random_set)
        self.random_button.pack(side='left',padx=(0,6))
        self.ordered_button = ttk.Button(row,text='按顺序开始学习',command=self.ordered_set)
        self.ordered_button.pack(side='left',padx=(0,6))
        self.selected_button = ttk.Button(row,text='用选中词条学习',command=self.selected_set)
        self.selected_button.pack(side='left')
    def build_study(self):
        self.study.columnconfigure(0, weight=1)
        self.study.rowconfigure(2, weight=1)
        self.progress = ttk.Label(self.study,font=('Arial',14))
        self.progress.grid(row=0, column=0, sticky='w', pady=(0,12))
        self.bar = ttk.Progressbar(self.study,maximum=100)
        self.bar.grid(row=1, column=0, sticky='ew', pady=(0,20))
        self.card = tk.Frame(self.study,bg='white',highlightbackground='#d6e1dd',highlightthickness=1,cursor='hand2')
        self.card.grid(row=2, column=0, sticky='nsew')
        self.english = tk.Label(self.card,bg='white',fg='#193e3b',font=('Arial',25,'bold'),wraplength=690)
        self.english.pack(expand=True,fill='both',padx=26,pady=(25,10))
        self.chinese = tk.Label(self.card,bg='white',fg='#486b62',font=('Arial',19),wraplength=690)
        self.chinese.pack(expand=True,fill='both',padx=26,pady=(0,20))
        for widget in (self.card,self.english,self.chinese): widget.bind('<Button-1>',lambda e:self.reveal())
        self.card.bind('<Configure>',lambda e:[w.configure(wraplength=max(240,e.width-60)) for w in (self.english,self.chinese)])
        self.hint = ttk.Label(self.study,text='点击卡片显示中文，然后选择熟悉程度。')
        self.hint.grid(row=3, column=0, pady=15)
        row = ttk.Frame(self.study)
        row.grid(row=4, column=0)
        self.yes = ttk.Button(row,text='熟悉 ✓',command=lambda:self.answer(True))
        self.no = ttk.Button(row,text='不熟悉 · 稍后再练',command=lambda:self.answer(False))
        self.yes.pack(side='left',padx=10)
        self.no.pack(side='left',padx=10)
        ttk.Button(self.study,text='返回收藏，选择新一套',command=lambda:self.tabs.select(self.library)).grid(row=5, column=0, pady=(20,0))
    def capture_help(self):
        messagebox.showinfo('选中即可收藏', '首次使用请运行升级包里的“安装划词收藏.command”。\n\n在网页或支持系统服务的桌面应用中：\n1. 选中英文。\n2. 右键 → 服务 → 收藏到英语卡片。\n也可从顶部应用菜单 → 服务中找到它。\n\n无需复制粘贴，也不用一直打开本窗口。翻译完成后英文和中文会一起保存。\n\n图片中的文字，以及不支持系统服务的应用，暂不支持此方式。')
    def update_count(self):
        ready=sum(w['status']=='ready' for w in self.store.words)
        self.count.configure(text=f'共 {len(self.store.words)} 条 · 可学 {ready} 条 · 已选 {len(self.tree.selection())} 条')
        if hasattr(self,'detail'):
            selected=set(self.tree.selection())
            errors=[w['error'] for w in self.store.words if w['id'] in selected and w['error']]
            self.detail.configure(text=errors[0] if errors else '按住 ⌘ / Shift 多选。双击词条可修改释义。仅翻译完成的词条参与学习。')
    def refresh(self):
        self.store.reload()
        selection = self.tree.selection()
        old_scroll = self.tree.yview()
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().casefold()
        labels={'ready':'已完成','pending':'等待翻译','translating':'翻译中…','error':'待重试'}
        for w in self.store.words:
            if not query or query in (w['en']+' '+w['zh']).casefold():
                self.tree.insert('', 'end',iid=w['id'],values=(w['en'],w['zh'],labels[w['status']]))
        self.tree.selection_set([i for i in selection if self.tree.exists(i)])
        if old_scroll: self.tree.yview_moveto(old_scroll[0])
        self.update_count()
    def poll(self):
        try:
            self.store.reload()
            signature=[(w['id'],w['updated'],w['status']) for w in self.store.words]
            if signature!=self.signature:
                self.refresh()
                self.signature=signature
            # A translation can finish while the initially empty study page is open.
            # Do not automatically restart a round just completed on this page.
            if self.tabs.select()==str(self.study) and not self.store.queue and self.store.total==0:
                self.ensure_study_queue(quiet=True)
            if self.card_state()!=self._card_state:
                self.render_card()
            if any(w['status'] in ('pending','translating') for w in self.store.words):
                if self.worker is None or self.worker.poll() is not None:
                    self.worker=launch_worker()
        finally:
            self.root.after(1500,self.poll)
    def retry_translation(self):
        ids=list(self.tree.selection())
        if not ids:
            messagebox.showinfo('重试翻译','请先选择状态为“待重试”的词条。'); return
        self.store.retry(ids)
        self.refresh()
        if self.worker is None or self.worker.poll() is not None:
            self.worker=launch_worker()
    def paste(self):
        try: value = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo('无法粘贴','请先复制一段英文。'); return
        self.en.delete('1.0','end'); self.en.insert('1.0',value)
        self.zh.focus_set()
    def clear(self):
        self.editing = None
        self.en.delete('1.0','end'); self.zh.delete('1.0','end')
        self.save_button.configure(text='加入收藏')
    def add(self):
        en,zh = self.en.get('1.0','end').strip(),self.zh.get('1.0','end').strip()
        try:
            if self.editing:
                self.store.edit(self.editing,en,zh)
            else:
                word_id,created=self.store.add(en,zh)
                if not created:
                    messagebox.showinfo('已收藏','这条英文已经存在，可以搜索后编辑中文释义。'); return
        except ValueError as e:
            messagebox.showinfo('检查一下内容',str(e)); return
        self.clear(); self.refresh(); self.render_card()
    def edit(self):
        ids = self.tree.selection()
        if len(ids)!=1:
            messagebox.showinfo('编辑词条','请只选择一条词条。'); return
        w = next(w for w in self.store.words if w['id']==ids[0])
        self.clear(); self.editing=w['id']
        self.en.insert('1.0',w['en']); self.zh.insert('1.0',w['zh'])
        self.save_button.configure(text='保存修改')
    def delete(self):
        ids = set(self.tree.selection())
        if not ids: return
        if not messagebox.askyesno('删除收藏',f'确定删除选中的 {len(ids)} 条收藏？'): return
        self.store.delete(ids)
        if self.editing in ids: self.clear()
        self.refresh(); self.render_card()
    def study_ids(self, ordered=False, quiet=False):
        try:
            count = int(self.study_count.get().strip())
            if count < 1:
                raise ValueError
        except ValueError:
            if not quiet:
                messagebox.showinfo('学习条数', '请在“每轮”中填写大于 0 的整数，例如 10、20 或 50。')
                self.tabs.select(self.library)
                self.count_input.focus_set()
            return None
        self.store.reload()
        ids = [w['id'] for w in self.store.words if w['status']=='ready']
        if ordered:
            # Store lists newest first (including rowid ties); learn oldest first.
            return list(reversed(ids))[:count]
        return random.sample(ids, min(count, len(ids)))
    def random_set(self):
        ids = self.study_ids()
        if ids is not None:
            self.start(ids)
    def ordered_set(self):
        ids = self.study_ids(ordered=True)
        if ids is not None:
            self.start(ids)
    def ensure_study_queue(self, quiet=False):
        self.store.reload()
        if self.store.queue:
            return
        ids = self.study_ids(quiet=quiet)
        if ids:
            self.store.start(ids)
    def on_tab_changed(self, event=None):
        tab = self.tabs.select()
        if tab == self._last_tab:
            return
        self._last_tab = tab
        if tab == str(self.study):
            self.ensure_study_queue()
            self.render_card()
        else:
            self.stop_speech()
    def card_state(self):
        current = self.store.queue[0] if self.store.queue else None
        word = next((w for w in self.store.words if w['id']==current), None)
        return (tuple(self.store.queue), self.store.done, self.store.total,
                (word['en'], word['zh']) if word else None,
                tuple((w['id'], w['status']) for w in self.store.words) if not current else ())
    def selected_set(self):
        self.store.reload()
        ready={w['id'] for w in self.store.words if w['status']=='ready'}
        self.start([i for i in self.tree.selection() if i in ready])
    def start(self,ids):
        if not ids:
            messagebox.showinfo('还没有词条','请先收藏英文并等待翻译完成，或选中已完成翻译的词条。'); return
        if self.store.queue and not messagebox.askyesno('开始新一套','当前练习尚未完成，要替换为新的一套吗？'): return
        self.store.start(ids); self.render_card(); self.tabs.select(self.study)
    def render_card(self):
        self.stop_speech()
        self.revealed=False
        s=self.store
        self._card_state=self.card_state()
        self.current_id=s.queue[0] if s.queue else None
        self.progress.configure(text=f'本轮已熟悉 {s.done} / {s.total} 条 · 待练 {len(s.queue)} 条')
        self.bar.configure(value=100*s.done/s.total if s.total else 0)
        active=bool(s.queue)
        for b in (self.yes,self.no): b.configure(state='normal' if active else 'disabled')
        if active:
            w=next(w for w in s.words if w['id']==s.queue[0])
            self.english.configure(text=w['en'],font=('Arial',25 if len(w['en'])<100 else 16,'bold'))
            self.chinese.configure(text='点击卡片，听英语并查看中文释义',font=('Arial',15))
            self.hint.configure(text='熟悉：移出本轮；不熟悉：放到队尾，稍后再次出现。')
        else:
            if s.total:
                title, detail = '本轮学习完成 ✓', '回到收藏，可以再选一套练习。'
            elif any(w['status'] in ('pending','translating') for w in s.words):
                title, detail = '正在等待中文翻译', '翻译完成后会自动开始学习。'
            elif s.words:
                title, detail = '还没有翻译完成的词条', '请回到收藏，选择待重试的词条并点击“重试翻译”。'
            else:
                title, detail = '开始你的第一套卡片', '先划词收藏英文，翻译完成后即可开始学习。'
            self.english.configure(text=title,font=('Arial',25,'bold'))
            self.chinese.configure(text=detail,font=('Arial',16))
            self.hint.configure(text='收藏会保留，随时可以再次练习。')
    def reveal(self):
        if not self.store.queue:return
        w=next(w for w in self.store.words if w['id']==self.store.queue[0])
        self.chinese.configure(text=w['zh'],font=('Arial',19 if len(w['zh'])<100 else 15))
        self.revealed=True
        self.speak(w['en'])
    def stop_speech(self):
        speech = getattr(self, '_speech', None)
        self._speech = None
        if speech is not None and speech.poll() is None:
            try:
                speech.terminate()
                try:
                    speech.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    speech.kill()
                    speech.wait(timeout=0.2)
            except (OSError, subprocess.TimeoutExpired):
                pass
    def speak(self, english):
        self.stop_speech()
        try:
            # The option terminator keeps collected text from becoming a command option.
            self._speech = subprocess.Popen(
                ['/usr/bin/say', '-v', 'Samantha', '-r', '160', '--', english],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.hint.configure(text='暂时无法播放英语发音，中文释义仍可正常查看。')
    def close(self):
        self.stop_speech()
        self.root.destroy()
    def answer(self,known):
        self.store.answer(known,expected=self.current_id); self.render_card()

def main():
    root=tk.Tk()
    # Tk on macOS uses iconphoto for the running application's Dock tile.
    icon_path = Path(__file__).with_name('landscape.png')
    if icon_path.exists():
        try:
            root._app_icon = tk.PhotoImage(master=root, file=str(icon_path))
            root.iconphoto(True, root._app_icon)
        except tk.TclError:
            pass  # An unavailable icon must not prevent access to saved cards.
    try: store=Store()
    except Exception as e:
        messagebox.showerror('无法读取收藏',f'收藏文件无法读取，程序不会覆盖原文件。\n{DATA_DIR}\n\n{e}')
        root.destroy(); return
    def error(kind,value,tb):
        messagebox.showerror('操作未完成',f'发生错误：{value}\n请检查磁盘空间及文件权限。')
    root.report_callback_exception=error
    App(root,store)
    root.mainloop()

if __name__=='__main__':main()
