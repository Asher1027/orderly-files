"""Small animated, rounded Tk controls; no image assets required."""
import tkinter as tk
import tkinter.font as font
import time
import math
from backdrop import paint_canvas_backdrop

BG = '#f5f5f7'
INK = '#25272b'
ACCENT = '#292c32'


def rounded(canvas, x1, y1, x2, y2, radius=16, **kwargs):
    r = max(0,min(radius, (x2-x1)/2, (y2-y1)/2))
    points=[]
    for cx,cy,start in ((x2-r,y1+r,-90),(x2-r,y2-r,0),(x1+r,y2-r,90),(x1+r,y1+r,180)):
        for step in range(13):
            angle=math.radians(start+step*90/12)
            points.extend((cx+r*math.cos(angle),cy+r*math.sin(angle)))
    return canvas.create_polygon(*points, **kwargs)


def mix(a, b, p):
    return '#' + ''.join(f'{round(int(a[i:i+2],16)*(1-p)+int(b[i:i+2],16)*p):02x}' for i in (1,3,5))


class AnimatedButton(tk.Canvas):
    def __init__(self, parent, text, command, primary=False):
        self.text, self.command, self.primary = text, command, primary
        self._state, self.hover, self.pressed = 'normal', False, False
        self.anim = None
        self.progress = 0
        self.font = font.Font(family='Microsoft YaHei UI', size=10)
        self.base = ACCENT if primary else '#e9eaee'
        super().__init__(parent, width=self.font.measure(text)+40, height=max(42,self.font.metrics('linespace')+22), bg=parent.cget('bg'), highlightthickness=0, bd=0, cursor='hand2', takefocus=1)
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self.animate(True))
        self.bind('<Leave>', lambda e: self.animate(False))
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', lambda e: self.draw())
        self.bind('<FocusOut>', lambda e: self.draw())
        self.bind('<Destroy>',lambda e:self.after_cancel(self.anim) if e.widget==self and self.anim else None)

    def configure(self, cnf=None, **kw):
        if 'state' in kw:
            self._state = kw.pop('state')
        if 'text' in kw:
            self.text = kw.pop('text')
        result = super().configure(cnf, **kw)
        self.draw()
        return result

    config = configure

    def cget(self, key):
        return self._state if key == 'state' else super().cget(key)

    def draw(self):
        self.delete('all')
        paint_canvas_backdrop(self)
        w,h = self.winfo_width(),self.winfo_height()
        inset = 3 if self.pressed else 1
        color = mix(self.base, '#454a52' if self.primary else '#dcdfe5', self.progress)
        if self._state == 'disabled':
            color = '#eceef1'
        rounded(self,inset,inset,w-inset,h-inset,(h-2*inset)/2, fill=color, outline=ACCENT if self.focus_get()==self else '', width=2)
        self.create_text(w/2,h/2+(1 if self.pressed else 0),text=self.text,font=self.font,fill='#9ba5b9' if self._state=='disabled' else ('white' if self.primary else INK))

    def animate(self, hover):
        self.hover = hover
        if not hover:
            self.pressed = False
        if self.anim:
            self.after_cancel(self.anim)
        start, end, began = self.progress, float(hover), time.monotonic()
        def tick():
            t = min(1,(time.monotonic()-began)/0.14)
            self.progress = start+(end-start)*(1-(1-t)**3)
            self.draw()
            self.anim = self.after(16,tick) if t<1 else None
        tick()

    def press(self, event):
        if self._state != 'disabled':
            self.focus_set()
            self.pressed = True
            self.draw()

    def release(self, event):
        fire = self.pressed and 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height()
        self.pressed=False
        self.draw()
        if fire:
            self.invoke()

    def invoke(self):
        if self._state != 'disabled':
            self.command()


class AnimatedTabs(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent,bg=BG)
        self.nav=tk.Frame(self,bg=BG)
        self.nav.pack(fill='x',pady=(0,12))
        self.body=tk.Frame(self,bg=BG)
        self.body.pack(fill='both',expand=True)
        self.pages=[]
        self.buttons=[]
        self.active=0
        self.anim=None
        self.bind('<Destroy>',lambda e:self.after_cancel(self.anim) if e.widget==self and self.anim else None)

    def add(self,page,text):
        index=len(self.pages)
        self.pages.append(page)
        button=AnimatedButton(self.nav,text,lambda:self.select(index),index==0)
        button.pack(side='left',padx=(0,8))
        self.buttons.append(button)
        if index==0:
            page.place(in_=self.body,x=0,y=0,relwidth=1,relheight=1)

    def select(self,index=None):
        if index is None:
            return str(self.pages[self.active])
        if not isinstance(index,int):
            index=next(i for i,p in enumerate(self.pages) if str(p)==str(index))
        if self.anim:
            self.after_cancel(self.anim)
        for page in self.pages:
            page.place_forget()
        self.active=index
        page=self.pages[index]
        for i,b in enumerate(self.buttons):
            b.primary=i==index
            b.base=ACCENT if b.primary else '#e9eaee'
            b.draw()
        began=time.monotonic()
        def tick():
            t=min(1,(time.monotonic()-began)/0.2)
            page.place(in_=self.body,x=0,y=round(18*(1-t)**3),relwidth=1,relheight=1)
            page.lift()
            self.anim=self.after(16,tick) if t<1 else None
        tick()


class FolderCard(tk.Canvas):
    COLORS = [('#edf0ff','#bdcaff','#dbe3ff'),('#fff4df','#efcf8c','#ffe6b0'),('#e8f6f0','#9edbc5','#c8eee0'),('#f5edff','#ceb6ed','#e4d5fa')]
    def __init__(self,parent,profile,index,select,drop,busy,scale=1,is_add=False):
        self.profile,self.select_cb,self.drop_cb,self.busy=profile,select,drop,busy
        self.selected=False
        self.level=0
        self.anim=None
        self.dragging=False
        self.is_add=is_add
        self.scale=scale
        self.phase=index*.9
        self.bob=0
        self.float_timer=None
        self.colors=self.COLORS[index%len(self.COLORS)]
        self.title_font=font.Font(family='Microsoft YaHei UI',size=11,weight='bold')
        super().__init__(parent,width=round((150 if is_add else 230)*scale),height=round(156*scale),bg=BG,highlightthickness=0,cursor='hand2',takefocus=1)
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Button-1>',lambda e:self.choose())
        self.bind('<Return>',lambda e:self.choose())
        self.bind('<space>',lambda e:self.choose())
        self.bind('<FocusIn>',lambda e:self.animate(1))
        self.bind('<FocusOut>',lambda e:self.animate(0))
        self.bind('<Enter>',lambda e:self.animate(1))
        self.bind('<Leave>',lambda e:self.animate(0))
        if drop:
            self.drop_target_register('DND_Files')
            self.dnd_bind('<<DropEnter>>',self.enter_drop)
            self.dnd_bind('<<DropPosition>>',lambda e:'copy' if not self.busy() else 'refuse_drop')
            self.dnd_bind('<<DropLeave>>',self.leave_drop)
            self.dnd_bind('<<Drop>>',self.drop)
        self.bind('<Destroy>',self.cleanup)
        self.float_timer=self.after(40,self.float_tick)

    def cleanup(self,event):
        if event.widget==self:
            for timer in (self.anim,self.float_timer):
                if timer:
                    self.after_cancel(timer)

    def float_tick(self):
        if self.winfo_viewable() and not self.busy():
            self.bob=math.sin(time.monotonic()*1.4+self.phase)*1.6*self.scale
            self.draw()
        self.float_timer=self.after(40 if self.winfo_viewable() else 180,self.float_tick)

    def choose(self):
        if not self.busy():
            self.focus_set()
            self.select_cb(self.profile['id'])

    def enter_drop(self,event):
        if self.busy():
            return 'refuse_drop'
        self.dragging=True
        self.animate(1)
        return 'copy'

    def leave_drop(self,event):
        self.dragging=False
        self.animate(0)

    def drop(self,event):
        self.dragging=False
        self.animate(0)
        if self.busy():
            return 'refuse_drop'
        paths=list(self.tk.splitlist(event.data))
        self.drop_cb(self.profile['id'],paths)
        # Only enqueue a preview. Explorer must not remove the source itself.
        return 'copy'

    def animate(self,end):
        if self.anim:
            self.after_cancel(self.anim)
        start,began=self.level,time.monotonic()
        def tick():
            t=min(1,(time.monotonic()-began)/0.24)
            self.level=start+(end-start)*(1-(1-t)**3)
            self.draw()
            self.anim=self.after(16,tick) if t<1 else None
        tick()

    def draw(self):
        self.delete('all')
        paint_canvas_backdrop(self)
        w,h=self.winfo_width(),self.winfo_height()
        if w<30 or h<30:
            return
        _,back,front=self.colors
        lift=7*self.scale*self.level+self.bob
        top=14*self.scale-lift
        bottom=h-15*self.scale-lift
        inset=8*self.scale
        for pad,color in ((5,'#f0f0f3'),(3,'#e9eaee'),(1,'#e2e4e9')):
            rounded(self,inset-pad,top+7*self.scale,w-inset+pad,bottom+6*self.scale+pad,22*self.scale,fill=mix(BG,color,.55+.25*self.level),outline='')
        edge='#9ab5d7' if self.selected or self.dragging else ('#d7dce4' if self.level>.1 else '#e7e9ee')
        rounded(self,inset,top,w-inset,bottom,21*self.scale,fill='#ffffff',outline=edge,width=1.5)
        if self.is_add:
            cx,cy=w/2,top+(bottom-top)*.43
            r=24*self.scale
            self.create_oval(cx-r,cy-r,cx+r,cy+r,fill=mix('#f2f3f6','#e8eef7',self.level),outline='')
            length=10*self.scale
            for coords in ((cx-length,cy,cx+length,cy),(cx,cy-length,cx,cy+length)):
                self.create_line(*coords,fill='#66768a',width=2*self.scale,capstyle='round')
            self.create_text(cx,bottom-35*self.scale,text='新增托管',font=('Microsoft YaHei UI',10),fill='#737b87')
            self.create_text(cx,bottom-17*self.scale,text='拖入已有文件夹',font=('Microsoft YaHei UI',8),fill='#8b919d')
            return
        x1,x2=w*.31,w*.69
        y=top+16*self.scale
        rounded(self,x1,y,x1+(x2-x1)*.48,y+20*self.scale,7*self.scale,fill=back,outline='')
        rounded(self,x1,y+9*self.scale,x2,y+47*self.scale,9*self.scale,fill=back,outline='')
        rounded(self,x1+5*self.scale,y+15*self.scale,x2-5*self.scale,y+43*self.scale,5*self.scale,fill='#ffffff',outline='')
        rounded(self,x1-2*self.scale,y+20*self.scale,x2+2*self.scale,y+49*self.scale,9*self.scale,fill=front,outline='')
        self.create_line(x1+9*self.scale,y+24*self.scale,x2-9*self.scale,y+24*self.scale,fill=mix(front,'#ffffff',.6),width=1)
        title=self.profile['name']
        while len(title)>1 and self.title_font.measure(title)>w-45*self.scale:
            title=title[:-2]+'…'
        self.create_text(w/2,bottom-43*self.scale,text=title,font=self.title_font,fill=INK)
        self.create_text(w/2,bottom-21*self.scale,text='松开以导入' if self.dragging else ('已选中' if self.selected else '拖入文件或文件夹'),font=('Microsoft YaHei UI',9),fill='#8b919d')
        if self.selected:
            cx,cy=w-inset-20*self.scale,top+19*self.scale
            self.create_oval(cx-7*self.scale,cy-7*self.scale,cx+7*self.scale,cy+7*self.scale,fill='#52667e',outline='')
            self.create_line(cx-3*self.scale,cy,cx-1*self.scale,cy+2*self.scale,cx+3*self.scale,cy-3*self.scale,fill='white',width=1.5,capstyle='round',joinstyle='round')


class RoundedPanel(tk.Frame):
    def __init__(self,parent,padx=16,pady=14):
        super().__init__(parent,bg=parent.cget('bg'))
        canvas=tk.Canvas(self,bg=self.cget('bg'),highlightthickness=0,bd=0)
        canvas.place(x=0,y=0,relwidth=1,relheight=1)
        self.content=tk.Frame(self,bg='white')
        self.content.pack(fill='both',expand=True,padx=padx,pady=pady)
        def draw(event):
            canvas.delete('all')
            paint_canvas_backdrop(canvas)
            rounded(canvas,0,0,event.width,event.height,22,fill='white',outline='')
        canvas.bind('<Configure>',draw)


class GradientWave(tk.Canvas):
    """A lightweight blue-violet wave backdrop inspired by the Codex landing page."""
    def __init__(self, parent, height=112):
        self.title_text = ''
        self.subtitle_text = ''
        super().__init__(parent, height=height, bg='#6679df', highlightthickness=0, bd=0)
        self.bind('<Configure>', self.paint)

    def set_text(self, title, subtitle):
        self.title_text, self.subtitle_text = title, subtitle
        self.paint()

    def paint(self, event=None):
        self.delete('all')
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        bands = [('#6b7fea', '#9b8ff0'), ('#536ee1', '#7f8deb'), ('#7889ed', '#c0aaf5')]
        for y in range(h):
            p = y / max(1, h - 1)
            a, b = bands[min(2, int(p * 3))]
            local = (p * 3) % 1
            self.create_line(0, y, w, y, fill=mix(a, b, local))
        self.create_oval(-w*.18, h*.18, w*.48, h*1.85, fill='#8ba5f1', outline='')
        self.create_oval(w*.43, -h*.9, w*1.08, h*.8, fill='#7a76e7', outline='')
        self.create_oval(w*.68, h*.2, w*1.22, h*1.95, fill='#a99af2', outline='')
        self.create_line(-w*.05, h*.64, w*.36, h*.3, w*.72, h*.76, w*1.08, h*.4,
                         smooth=True, splinesteps=36, fill='#d9d9fb', width=max(1, round(h*.06)))
        self.create_line(-w*.08, h*.78, w*.28, h*.52, w*.62, h*.9, w*1.1, h*.58,
                         smooth=True, splinesteps=36, fill='#7189ea', width=max(1, round(h*.08)))
        if self.title_text:
            self.create_text(28, 34, text=self.title_text, anchor='w', fill='white', font=('Microsoft YaHei UI', 20, 'bold'))
            self.create_text(28, 72, text=self.subtitle_text, anchor='w', fill='#eef0ff', font=('Microsoft YaHei UI', 10))
