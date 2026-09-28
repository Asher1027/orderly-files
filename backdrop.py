"""One continuous procedural blue/violet wave, sampled behind Tk surfaces."""
import math
import tkinter as tk
from PIL import Image, ImageTk


class WaveBackdrop:
    def __init__(self, root, background):
        self.root, self.background = root, background
        self.size = None
        self.image = None
        self.surfaces = {}
        self.seed = self.make_wave()
        self.timer = root.after(80, self.refresh)
        root.bind('<Destroy>', self.close, add='+')

    def close(self, event):
        if event.widget == self.root and self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None

    def make_wave(self):
        width,height=480,340
        image=Image.new('RGB',(width,height))
        pixels=[]
        for j in range(height):
            y=j/(height-1)
            for i in range(width):
                x=i/(width-1)
                # Broad luminous crest, deep blue at left, violet at right.
                crest=.24+.22*math.sin(3.8*y-.7)
                glow=math.exp(-((x-crest)/.26)**2)
                violet=math.exp(-((x-.88)/.3)**2)
                base=(114+27*x,145-18*x,229+7*x)
                white=min(.86,.13+.72*glow+.12*y)
                color=[base[k]*(1-white)+(244,243,255)[k]*white for k in range(3)]
                color=[v*(1-.24*violet)+c*.24*violet for v,c in zip(color,(135,114,240))]
                ribbon=math.exp(-((x-(.08+.50*y+.06*math.sin(y*8)))/.06)**2)
                shimmer=math.sin((x*1.2-y)*170)*math.sin((x+y)*97)*1.6*glow
                color=[min(255,max(0,round(v+14*ribbon+shimmer))) for v in color]
                pixels.append(tuple(color))
        image.putdata(pixels)
        return image

    def walk(self, widget):
        if isinstance(widget,tk.Toplevel) and widget is not self.root:
            return
        yield widget
        for child in widget.winfo_children():
            if not getattr(child,'_wave_layer',False):
                yield from self.walk(child)

    def refresh(self):
        size=(max(1,self.root.winfo_width()),max(1,self.root.winfo_height()))
        if size != self.size:
            self.size=size
            self.image=self.seed.resize(size,Image.Resampling.BICUBIC)
        for widget in list(self.walk(self.root)):
            try:
                if widget.cget('bg') != self.background:
                    continue
            except tk.TclError:
                continue
            if not isinstance(widget,(tk.Tk,tk.Toplevel,tk.Frame,tk.Canvas,tk.Label)):
                continue
            x=widget.winfo_rootx()-self.root.winfo_rootx()
            y=widget.winfo_rooty()-self.root.winfo_rooty()
            w,h=widget.winfo_width(),widget.winfo_height()
            key=(size,x,y,w,h)
            old=self.surfaces.get(widget)
            if old and old[0]==key and (old[2] is None or old[2].winfo_exists()):
                continue
            if w<2 or h<2:
                continue
            photo=ImageTk.PhotoImage(self.image.crop((x,y,x+w,y+h)),master=self.root)
            if isinstance(widget,tk.Canvas):
                widget._wave_photo=photo
                widget.delete('_wave')
                widget.create_image(0,0,image=photo,anchor='nw',tags='_wave')
                widget.tag_lower('_wave')
                layer=None
            elif isinstance(widget,tk.Label):
                widget.configure(image=photo,compound='center',bd=0,padx=0,pady=0)
                layer=None
            else:
                layer=old[2] if old and old[2] is not None and old[2].winfo_exists() else tk.Label(widget,bd=0,highlightthickness=0)
                layer._wave_layer=True
                layer.configure(image=photo)
                px=int(widget.cget('padx')) if isinstance(widget,tk.Frame) else 0
                py=int(widget.cget('pady')) if isinstance(widget,tk.Frame) else 0
                layer.place(x=-px,y=-py,width=w,height=h)
                layer.lower()
            self.surfaces[widget]=(key,photo,layer)
        for widget in list(self.surfaces):
            if not widget.winfo_exists():
                del self.surfaces[widget]
        self.timer=self.root.after(180,self.refresh)


def paint_canvas_backdrop(canvas):
    photo=getattr(canvas,'_wave_photo',None)
    if photo:
        canvas.create_image(0,0,image=photo,anchor='nw',tags='_wave')
