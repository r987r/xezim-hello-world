"""Generate deterministic, self-contained 2D SVG diagrams from validated SoC metadata.

No web service, Mermaid runtime, Graphviz, Pillow, or 3D dependencies.
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
            x0,y0=coords[-2]; x1,y1=coords[-1]
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

def arch_svg(cfg,meta,path:Path):
    compute=[s for s in meta['subsystems'] if s['type']=='compute']
    cols=min(2,max(1,len(compute)))
    rows=(len(compute)+cols-1)//cols
    card_w=636 if cols==2 else 1312
    cw=card_w
    row_gap=338
    global_y=146+rows*row_gap+18
    memory_y=global_y+176
    H=memory_y+411
    a=Art(1440,H)
    a.heading('Architecture · configuration intent','Hierarchical SoC architecture',
              'Generated from config/soc.yaml • dashed = planned integration • solid = RTL-tested memory path')
    for i,s in enumerate(compute):
        col=i%cols;row=i//cols
        x=64+col*(card_w+40);y=162+row*row_gap
        a.rect(x,y,cw,310,fill=WHITE,outline=FAINT,r=18,width=2)
        a.text(x+20,y+13,s['name']+'  /  compute subsystem',22,INK)
        a.badge(x+cw-151,y+14,'SELECTED IP','selected',w=128)
        half=(cw-60)/2
        cpu=s['cpu'];dma=cfg['subsystem_types']['compute']['dma']
        a.box_label(x+20,y+55,half,88,cpu['ip'],cpu['bus']+'  ·  '+cpu['adapter'],kind='cpu')
        a.box_label(x+40+half,y+55,half,88,dma,'DMA integration pending',kind='dma')
        a.box_label(x+20,y+159,half,83,'Local data fabric',cfg['fabrics']['local_data']['backend']+'  ·  pending',kind='fabric')
        a.box_label(x+40+half,y+159,half,83,'Local config fabric',cfg['fabrics']['local_config']['backend']+'  ·  pending',kind='config')
        addr=next((z for z in meta['data_regions'] if z['name']==s['name']+'.sram'),None)
        tail=(f"0x{addr['base']:x} · size 0x{addr['size']:x}" if addr else 'unmapped')
        a.rect(x+20,y+258,cw-40,38,fill=ORANGE_BG,outline='#E8C29C',r=9,width=1)
        a.text(x+32,y+265,'Local SRAM  ·  '+tail,16,INK)
    a.box_label(64,global_y,636,120,'Global DATA NoC',
                cfg['fabrics']['global_data']['backend']+'  /  '+cfg['fabrics']['global_data']['topology']+'  ·  AXI4 '+str(meta['data_bits'])+'-bit\nPlanned RTL integration',kind='fabric',title_size=24,detail_size=16)
    a.box_label(740,global_y,636,120,'Global CONFIG NoC',
                cfg['fabrics']['global_config']['backend']+'  /  '+cfg['fabrics']['global_config']['topology']+'  ·  AXI4-Lite\nPlanned RTL integration',kind='config',title_size=24,detail_size=16)
    for i,s in enumerate(compute):
        x=64+(i%cols)*(card_w+40)
        y=162+(i//cols)*row_gap+310
        a.line([(x+205,y),(x+205,y+22),(300,global_y-12),(300,global_y)],BLUE,2,True,True)
        a.line([(x+470,y),(x+470,y+12),(1058,global_y-12),(1058,global_y)],PURPLE,2,True,True)
    a.rect(64,memory_y,1312,340,fill=WHITE,outline=FAINT,r=18,width=2)
    memname=meta['memory_subsystem']
    a.text(88,memory_y+19,memname+'  /  heterogeneous memory subsystem',24,INK)
    a.badge(1200,memory_y+19,'RTL TESTED','tested',w=137)
    ni=meta['ingress'];np=min(ni,6)
    for i in range(np):
        x=112+i*155
        a.rect(x,memory_y+74,139,42,fill=BLUE_BG,outline=BLUE,r=9,width=1)
        a.text(x+69,memory_y+85,'AXI ingress '+str(i),16,BLUE,align='center')
        a.line([(x+69,memory_y+116),(x+69,memory_y+142)],GREEN,2,False,True)
    a.box_label(112,memory_y+142,935,68,'Local AXI data crossbar',
                cfg['fabrics']['memory_data']['backend']+f" · {ni} ingress × {len(meta['targets'])} targets · verified fabric",'rtl',title_size=22,detail_size=15)
    a.box_label(1070,memory_y+142,265,68,'Config registers',
                'CSR wiring pending','config',title_size=17,detail_size=13)
    mem_targets=meta['targets'];tgap=18;total_w=935;t_w=(total_w-(len(mem_targets)-1)*tgap)/len(mem_targets)
    for j,t in enumerate(mem_targets):
        x=112+j*(t_w+tgap)
        a.line([(x+t_w/2,memory_y+210),(x+t_w/2,memory_y+239)],GREEN,2,False,True)
        a.box_label(x,memory_y+241,t_w,79,f"{t['name']}  ·  {t['kind'].upper()}",
                    f"{t['controller']}  |  sim: {t['sim_backend']}\n0x{t['base']:x}  ·  size 0x{t['size']:x}",'memory',title_size=17,detail_size=14)
    for i in range(min(ni, 6)):
        x_ingress=112+i*155+69
        x_port=235+i*185
        a.line([(x_port,global_y+120),(x_port,global_y+143),
                (x_ingress,memory_y+40),(x_ingress,memory_y+74)],BLUE,3,True,True)
    a.text(565,global_y+136,f'{meta["ingress"]} AXI output ports',15,MUTED)
    a.line([(1100,global_y+120),(1100,memory_y+142)],PURPLE,3,True,True)
    # Keep the long subsystem title readable above crossing dashed uplink routes.
    a.rect(80,memory_y+12,610,44,fill=WHITE,outline=WHITE,r=0,width=0)
    a.text(88,memory_y+19,memname+'  /  heterogeneous memory subsystem',24,INK)
    a.line([(64,memory_y+352),(1376,memory_y+352)],FAINT,1)
    a.text(74,memory_y+357,'Current scope: real 2×2 AXI RAM testbench. Global/local networks, real DMA, and controller PHYs remain planned.',15,MUTED)
    a.save(path)


def rtl_svg(cfg,meta,path:Path):
    a=Art(1440,820)
    a.heading('RTL connectivity · executable scope','Memory fabric: actual SystemVerilog wiring',
              'Generated memory_tb.sv • 2 AXI masters → Verilog-AXI crossbar → HBM0 / DDR0 behavioral targets')
    a.rect(64,161,1312,550,fill=WHITE,outline=FAINT,r=20,width=2)
    a.text(91,185,'EXISTING MEMORY TESTBENCH',18,BLUE)
    ni=meta['ingress'];ts=meta['targets'];ty=[283,445]
    for i in range(ni):
        y=ty[i] if i<len(ty) else 282+i*90
        a.box_label(96,y,310,101,'AXI master BFM '+str(i),
                    f"AW / W / B / AR / R\n{meta['data_bits']}-bit · ID {meta['id_bits']}","cpu",title_size=22,detail_size=16)
        a.line([(406,y+49),(528,y+49)],BLUE,3,False,True)
        a.text(413,y+17,'AXI4 ingress '+str(i),15,MUTED)
    a.box_label(529,330,377,151,'axi_crossbar',
                f"{ni} inputs  ×  {len(ts)} outputs\n{meta['address_bits']}-bit addresses\n{meta['data_bits']}-bit data · real open-source RTL",'rtl',title_size=28,detail_size=17)
    for j,t in enumerate(ts):
        y=ty[j] if j<len(ty) else 282+j*90
        a.box_label(1028,y,316,101,f"{t['name']} · {t['kind'].upper()}",
                    f"{t['sim_backend']} AXI model\n0x{t['base']:x} / 0x{t['size']:x}",'memory',title_size=19,detail_size=16)
        a.line([(906,y+52),(1028,y+52)],GREEN,3,False,True)
        a.text(912,y+22,'AXI4 output '+str(j),15,MUTED)
    a.box_label(545,562,339,86,'Passive AXI route monitor',
                'Checks ID, source, target and address','neutral',title_size=20,detail_size=15)
    a.line([(714,481),(714,562)],GRAY,2,True,True)
    a.text(92,674,'Only these solid AXI connections are executable today; CPU/DMA and global fabric paths are not yet integrated.',16,MUTED)
    a.line([(64,747),(1376,747)],FAINT,2)
    a.text(74,761,'Protocol: AXI4 · Read / write bursts · 2 source ingress ports · 2 independently addressed targets',18,INK)
    a.save(path)


def verif_svg(cfg,meta,path:Path):
    scopes=cfg['verification']['scopes']
    impl=[s for s in scopes if s['status']=='executable']
    planned=[s for s in scopes if s['status']!='executable']
    impl_rows = (len(impl)+1)//2
    plan_y=max(605, 159+70+impl_rows*163+28)
    H=max(1020, plan_y+68+((len(planned)+1)//2)*121+115)
    a=Art(1440,H)
    a.heading('Verification · generated coverage scope','Hierarchical verification plan',
              'Green = executable testbench exists • Grey = planned • status does not imply successful silicon verification')
    a.box_label(64,237,292,103,'config/soc.yaml','Single architecture source','config',title_size=22,detail_size=16)
    a.box_label(405,237,260,103,'make gen','SV + NoC IR + route plans\n2D diagrams + README','fabric',title_size=24,detail_size=15)
    a.line([(356,286),(405,286)],BLUE,3,False,True)
    a.line([(665,286),(722,286)],GREEN,3,False,True)
    a.rect(725,159,651,70+impl_rows*163,WHITE,GREEN,r=17,width=2)
    a.text(749,180,'EXISTING TEST SCOPES',23,GREEN)
    for i,s in enumerate(impl):
        col=i%2;row=i//2
        x=749+col*311;y=227+row*163
        title=s['name'].replace('_',' ')
        info=f"DUT: {s['dut']}\n{s.get('command','') or 'configured'}"
        a.box_label(x,y,292,132,title,info,'rtl',title_size=20,detail_size=16)
    rows=(len(planned)+1)//2
    a.rect(725,plan_y,651,68+rows*121,WHITE,GRAY,r=17,width=2)
    a.text(749,plan_y+19,'PLANNED TEST SCOPES',23,GRAY)
    for i,s in enumerate(planned):
        col=i%2;row=i//2
        x=749+col*311;y=plan_y+67+row*121
        a.box_label(x,y,292,96,s['name'].replace('_',' '),
                    f"DUT: {s['dut']}\nnot integrated",'planned',title_size=19,detail_size=14)
    a.rect(64,427,601,162,WHITE,FAINT,r=15,width=2)
    a.text(88,453,'Testbench composition',22,INK)
    a.text(88,498,f'{meta["ingress"]} AXI active BFMs + {len(meta["targets"])} simulated memory targets',18,MUTED)
    a.text(88,535,'CPU smoke: real PicoRV32 and SERV RTL fetch checks',18,MUTED)
    a.text(64,H-63,'Planned verification is generated from the same config, not asserted as implemented RTL.',16,MUTED)
    a.save(path)


def subsystem_svg(cfg,meta,inst,path:Path):
    a=Art(1220,630)
    name=inst['name'];typ=inst['type']
    a.heading('Subsystem · configurable boundary',name+'  /  '+typ,
              'Generated from config/soc.yaml • dashed links = future subsystem RTL integration')
    a.rect(64,160,1092,408,WHITE,FAINT,r=18,width=2)
    if typ=='compute':
        cpu=inst['cpu'];dma=cfg['subsystem_types']['compute']['dma']
        a.box_label(104,216,420,95,'CPU · '+cpu['ip'],cpu['bus']+' / '+cpu['adapter'],'cpu')
        a.box_label(641,216,431,95,'DMA · '+dma,'selected; RTL integration pending','dma')
        a.box_label(104,379,420,96,'Local AXI data NoC',cfg['fabrics']['local_data']['backend']+' (selected)','fabric')
        a.box_label(641,379,431,96,'Local config fabric',cfg['fabrics']['local_config']['backend']+' (selected)','config')
        a.line([(313,311),(313,379)],BLUE,3,True,True)
        a.line([(850,311),(850,379)],PURPLE,3,True,True)
        addr=next((z for z in meta['data_regions'] if z['name']==name+'.sram'),None)
        if addr:
            a.text(106,507,f"SRAM address: 0x{addr['base']:x} · size: 0x{addr['size']:x}",18,MUTED)
    else:
        ni=meta['ingress'];ts=meta['targets']
        for i in range(ni):
            a.box_label(105+i*375,200,329,80,'AXI ingress '+str(i),'from global data network (planned)','cpu',title_size=21,detail_size=14)
            a.line([(267+i*375,280),(267+i*375,323)],BLUE,3,True,True)
        a.box_label(105,323,932,83,'Local AXI data crossbar',
                    cfg['fabrics']['memory_data']['backend']+f" / {ni}×{len(ts)} · executed memory test",'rtl')
        w=(932-18*(len(ts)-1))/len(ts)
        for j,t in enumerate(ts):
            x=105+j*(w+18)
            a.line([(x+w/2,406),(x+w/2,427)],GREEN,3,False,True)
            a.box_label(x,427,w,98,t['name']+' · '+t['kind'].upper(),
                        f"{t['controller']} (candidate)\n{t['sim_backend']} model / 0x{t['base']:x}",'memory',title_size=20,detail_size=15)
    a.save(path)



def boot_svg(cfg,meta,path:Path):
    import bootgen
    a0=bootgen.build(cfg)['addresses']
    policy=cfg['boot']
    a=Art(1440,990)
    a.heading('Boot · executable scope','CPU0 Boot ROM loads two SRAMs',
              f'Boot: {policy["strategy"]} / {policy["image_source"]} / {policy["secondary_release"]} | no dedicated boot CPU | no global NoC')
    a.box_label(80,186,380,105,'Power-on reset',f'{policy["primary"]} active / {policy["secondary"]} held in reset','config',title_size=24)
    a.box_label(530,186,380,105,'PicoRV32 executes Boot ROM',
                f'0x{a0["bootrom"]:08x} | real instruction fetch','cpu',title_size=21)
    a.line([(460,238),(530,238)],BLUE,3,False,True)
    a.box_label(955,186,395,105,'Mapped flash model (not QSPI)',
                f'0x{a0["flash"]:08x} | read-only, hex initialized','memory',title_size=22)
    a.line([(910,238),(955,238)],BLUE,3,False,True)
    a.rect(80,346,1270,224,WHITE,FAINT,r=20,width=2)
    a.text(109,359,'boot_local_decode RTL routes CPU0 AXI-Lite reads/writes to dual-port SRAM RTL',21,INK)
    a.box_label(125,423,535,112,'SRAM0: CPU0 firmware',
                f'0x{a0["sram0"]:08x} | uninitialized SRAM RTL, then {policy["program_words"]} stores','memory',title_size=22)
    a.box_label(770,423,535,112,'SRAM1: SERV firmware',
                f'0x{a0["sram1"]:08x} | uninitialized SRAM RTL, then {policy["program_words"]} stores','memory',title_size=22)
    a.line([(1130,291),(1130,423)],ORANGE,3,False,True)
    a.line([(1060,291),(650,394),(392,423)],ORANGE,3,False,True)
    a.box_label(80,642,535,112,'CPU0 executes SRAM0 program',
                f'Writes 0x55 to 0x{a0["signature0"]:08x}','rtl',title_size=21)
    a.box_label(765,642,535,112,'CPU1 executes SRAM1 program',
                f'Writes 0x66 to 0x{a0["signature1"]:08x}','rtl',title_size=21)
    a.line([(393,535),(393,642)],GREEN,3,False,True)
    a.line([(1038,535),(1038,642)],GREEN,3,False,True)
    a.box_label(80,812,1220,104,'Boot control CSR + scoreboard',
                f'CPU0 store 0x{a0["reset_ctrl"]:08x}=1 releases CPU1. Test requires flash reads, SRAM writes, both signatures.',
                'config',title_size=23,detail_size=17)
    a.line([(1038,754),(1038,812)],PURPLE,2,False,True)
    a.text(91,931,'Future: replace memory-mapped flash model with QSPI; integrate real local/global NoC and DMA.',18,MUTED)
    a.save(path)

def render_images(cfg,meta,output_dir:Path):
    arch_svg(cfg,meta,output_dir/'architecture.svg')
    rtl_svg(cfg,meta,output_dir/'rtl-connectivity.svg')
    verif_svg(cfg,meta,output_dir/'verification.svg')
    boot_svg(cfg,meta,output_dir/'boot.svg')
    for inst in meta['subsystems']:
        subsystem_svg(cfg,meta,inst,output_dir/'subsystems'/f"{inst['name']}.svg")
