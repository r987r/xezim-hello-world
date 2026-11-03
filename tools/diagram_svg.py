"""Generate deterministic, self-contained 2D SVG diagrams from validated SoC metadata.

No web service, Mermaid runtime, Graphviz, Pillow, or 3D dependencies.\nOnly drawing primitives remain; the single full-SoC diagram is in noc_diagrams.py.
"""
from __future__ import annotations

from math import atan2, cos, sin, pi
from pathlib import Path
from xml.sax.saxutils import escape

BG = "#F7F9FC"
WHITE = "#FFFFFF"
INK = "#17253B"
MUTED = "#53657C"
FAINT = "#D8E1EB"
BLUE = "#255BAE"
BLUE_BG = "#E9F1FD"
GREEN = "#19734B"
GREEN_BG = "#E6F6EC"
PURPLE = "#7047B5"
PURPLE_BG = "#F3EDFD"
ORANGE = "#B66B22"
ORANGE_BG = "#FFF2E4"
GRAY = "#68778A"
GRAY_BG = "#F1F3F6"


class Art:
    def __init__(self, width, height, scale=1):
        self.width, self.height = width, height
        self.ops = [f'<rect width="{width}" height="{height}" fill="{BG}"/>']

    def rect(self, x, y, w, h, fill=WHITE, outline=FAINT, r=15, width=2):
        self.ops.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                        f'rx="{r:.1f}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>')

    def line(self, coords, color=MUTED, width=2, dashed=False, arrow=False):
        points = " ".join(f"{x:.1f},{y:.1f}" for x,y in coords)
        dash = ' stroke-dasharray="9 6"' if dashed else ""
        self.ops.append(f'<polyline points="{points}" fill="none" stroke="{color}" '
                        f'stroke-width="{width}" stroke-linecap="round" '
                        f'stroke-linejoin="round"{dash}/>')
        if arrow and len(coords)>1:
            ends = [(coords[-2], coords[-1])]
            if arrow == "both":
                ends.append((coords[1], coords[0]))
            for (x0,y0), (x1,y1) in ends:
                angle=atan2(y1-y0,x1-x0)
                size=10
                pts=[(x1,y1),
                     (x1-size*cos(angle-pi/6),y1-size*sin(angle-pi/6)),
                     (x1-size*cos(angle+pi/6),y1-size*sin(angle+pi/6))]
                pt=" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)
                self.ops.append(f'<polygon points="{pt}" fill="{color}"/>')

    def text(self,x,y,value,size=18,color=INK,align="left",spacing=1.35):
        value = (str(value).replace('•', ' | ').replace('×', 'x')
                 .replace('→', ' -> ').replace('·', ' - ').replace('—', ' - '))
        anchor = 'middle' if align=='center' else ('end' if align=='right' else 'start')
        for i, line in enumerate(value.split('\n')):
            yy=y+i*size*spacing
            self.ops.append(f'<text x="{x:.1f}" y="{yy:.1f}" font-size="{size}" '
                            f'font-family="Arial, Helvetica, sans-serif" '
                            f'fill="{color}" text-anchor="{anchor}" '
                            f'dominant-baseline="hanging">{escape(line)}</text>')

    def heading(self,kicker,title,subtitle):
        self.text(64,28,kicker.upper(),15,BLUE)
        self.text(64,55,title,32,INK)
        self.text(64,101,subtitle,18,MUTED)
        self.line([(64,137),(self.width-64,137)],color=FAINT,width=2)

    def badge(self,x,y,value,kind="planned",w=None):
        c,b = (GREEN,GREEN_BG) if kind=="tested" else (PURPLE,PURPLE_BG) if kind=="selected" else (GRAY,GRAY_BG)
        w=w or 16+len(value)*10
        self.rect(x,y,w,27,fill=b,outline=b,r=8,width=1)
        self.text(x+10,y+5,value,13,c)
        return w

    def box_label(self,x,y,w,h,title,detail="",kind="neutral",title_size=21,detail_size=15):
        styles={"cpu":(BLUE_BG,BLUE),"dma":(BLUE_BG,BLUE),"fabric":(GREEN_BG,GREEN),
                "config":(PURPLE_BG,PURPLE),"memory":(ORANGE_BG,ORANGE),
                "rtl":(GREEN_BG,GREEN),"neutral":(WHITE,FAINT),"planned":(GRAY_BG,GRAY)}
        bg,accent=styles[kind]
        self.rect(x,y,w,h,fill=bg,outline=accent if kind!="neutral" else FAINT,r=12,width=1)
        self.text(x+16,y+12,title,title_size,INK)
        if detail:
            self.text(x+16,y+44,detail,detail_size,MUTED,spacing=1.3)

    def save(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
             f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
             f'role="img" aria-label="Generated two-dimensional SoC diagram">\n'
             + "\n".join(self.ops)+"\n</svg>\n")
        path.write_text(svg, encoding="utf-8")

