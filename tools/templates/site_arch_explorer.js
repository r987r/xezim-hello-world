(() => {
"use strict";
const g=JSON.parse(document.getElementById("ex-embedded-graph").textContent);
const inventory=JSON.parse(document.getElementById("ex-embedded-signals").textContent);
const parsed=JSON.parse(document.getElementById("ex-embedded-rtl").textContent);
const linkRuns=JSON.parse(document.getElementById("arch-embedded-protocol-links").textContent);
const svg=document.getElementById("arch-svg"),vp=document.getElementById("arch-viewport"),status=document.getElementById("arch-status");
const crumbs=document.getElementById("arch-crumbs"),profile=document.getElementById("arch-profile"),plane=document.getElementById("arch-plane");
const facts=document.getElementById("arch-inspect-facts"),subtitle=document.getElementById("arch-inspect-subtitle"),title=document.getElementById("arch-inspect-title"),open=document.getElementById("arch-inspect-open");
const NS="http://www.w3.org/2000/svg",C={data:"#28b8b3",config:"#a78bfa",ip:"#5b829f",planned:"#d8a15c",bg:"#081522",text:"#eaf4ff",muted:"#a0bdd1"};
const nodes=new Map(g.nodes.map(n=>[n.id,n])),groups=new Map(g.groups.map(q=>[q.name,q]));
const nets=new Map(g.groups.filter(q=>["data","config"].includes(q.info?.plane)).map(q=>[q.name,q]));
const subs=g.groups.filter(q=>q.name.endsWith("_subsystem"));
const subName=q=>q.name.slice(0,-10);
const memberOf=new Map;subs.forEach(q=>q.instances.forEach(n=>memberOf.set(n,subName(q))));
const networkOf=id=>{for(const n of nets.keys())if(id.startsWith(n+"."))return n;return null};
const networksOf=id=>[...nets.keys()].filter(n=>n.startsWith(id+"_"));
const color=n=>nets.get(n)?.info?.plane==="config"?C.config:C.data,clip=(s,n)=>String(s).length>n?String(s).slice(0,n-1)+"…":String(s);
const short=id=>String(id).split(".").slice(-1)[0];
// Logical diagram node -> parsed module; this is a syntax-only association.
// Preserve test-profile-dependent RTL composition as a separate concern.
const parsedModules=new Map((parsed.modules||[]).map(m=>[m.name,m]));
const moduleCandidates=id=>{
  const n=nodes.get(id),ip=n?.info?.ip||"";
  const preferred={
    "ethernet0.ip":["ethernet0_axi_mvp","ethernet0_mvp"],
    "pcie0.ip":["pcie_tlp_bridge"],
    "compute0.cpu":["picorv32_cpu_adapter"],
    "compute1.cpu":["serv_cpu_adapter"],
    "compute0.dma":["soc_idma_engine"],"compute1.dma":["soc_idma_engine"],
    "compute0.dma_csr":["soc_dma_regs"],"compute1.dma_csr":["soc_dma_regs"],
    "compute0.sram":["axi_sram_target"],"compute1.sram":["axi_sram_target"],
    "pcie0.sram":["axi_sram_target"],"ethernet0.sram":["axi_sram_target"]
  };
  return [...new Set([...(preferred[id]||[]),ip,n?.module].filter(Boolean))];
};
const ipModule=id=>moduleCandidates(id).find(x=>parsedModules.has(x))||null;
const ipDestination=id=>({mode:"ip",name:id});

const actorFor=n=>{
  const id=n?.id||"";
  const p=g.profiles[profile.value]||{};
  const actors=p.actors||{};
  if(actors[id])return actors[id];
  const m=id.match(/^([^.]+)\.(cpu|dma|sram|dma_csr|reset_ctrl|ctrl)$/);
  if(!m)return null;
  const suffix=m[2]==="dma_csr"?"dma_regs":m[2]==="ctrl"?"controller_regs":m[2];
  return actors[m[1]+"_local_data."+suffix]||actors[m[1]+"_local_config."+suffix]||null;
};
const actorDisplay=n=>{
  const actor=actorFor(n);
  if(!actor)return null;
  const kind=actor.kind||"";
  if(kind==="verification_bfm")return "AXI verification BFM (test mode)";
  if(kind==="rtl_dma")return "Real PULP iDMA RTL (DMA mode)";
  if(kind==="rtl_cpu")return actor.short_label||"Real RTL CPU";
  if(kind==="rtl_registers")return "Real RTL CSR/register bank";
  if(kind==="reserved_idle")return "Reserved/disabled (this test mode)";
  if(kind==="reserved_error")return "DECERR placeholder (this test mode)";
  if(kind==="verification_target")return "Verification-only target";
  if(kind==="rtl_model")return actor.short_label||"RTL memory/ROM model";
  return actor.short_label||actor.label||kind;
};
const role=n=>{
  const mem=n?.info?.memory_integration;
  if(mem){
    const name=String(mem.kind||"memory").toUpperCase();
    return mem.soc_backend==="axi_ram"
      ?name+" · AXI RAM model in SoC"
      :name+" · "+String(mem.soc_backend||"unresolved")+" SoC backend";
  }
  return actorDisplay(n)||(n?.info?.ip||n?.info?.kind||n?.module||"RTL boundary");
};
const edgeType=e=>{
  // Determine the plane from the *generated NoC membership*, never by
  // substrings in an endpoint name (e.g. reset registers are not NoCs).
  const a=networkOf(e.from.instance),b=networkOf(e.to.instance);
  const pa=nets.get(a)?.info?.plane,pb=nets.get(b)?.info?.plane;
  if(pa&&pb&&pa!==pb)return "unclassified";
  return pa||pb||"unclassified";
};
let current="chip",scope="",dims={w:1530,h:965},zoom=1,next=null;
const elem=(t,attrs={},label)=>{const n=document.createElementNS(NS,t);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(label!==undefined)n.textContent=String(label);return n;};
const add=(p,n)=>{p.append(n);return n;};
const text=(p,x,y,s,size=12,c=C.text,weight=400,anchor="start")=>add(p,elem("text",{x,y,fill:c,"font-size":size,"font-family":"system-ui,Segoe UI,sans-serif","font-weight":weight,"text-anchor":anchor},s));
const box=(p,x,y,w,h,fill="#12253a",stroke="#3b5e79",r=10,sw=1.4,dash="")=>add(p,elem("rect",{x,y,width:w,height:h,rx:r,fill,stroke,"stroke-width":sw,...(dash?{"stroke-dasharray":dash}:{})}));
const route=(p,pts,c=C.data,w=3,dash="")=>add(p,elem("path",{d:pts.map((pt,i)=>(i?"L":"M")+pt[0]+" "+pt[1]).join(" "),stroke:c,"stroke-width":w,fill:"none","stroke-linejoin":"round","stroke-linecap":"round",...(dash?{"stroke-dasharray":dash}:{})}));
function clickable(n,item,dest){
  n.setAttribute("class","arch-click");n.setAttribute("tabindex","0");n.setAttribute("role","button");n.setAttribute("aria-label",item.title||item.kind||"Select diagram item");
  n.addEventListener("click",e=>{e.stopPropagation();if(dest?.mode==="ip")navigate(dest.mode,dest.name);else inspect(item,dest)});
  n.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();if(dest?.mode==="ip")navigate(dest.mode,dest.name);else inspect(item,dest)}});
  if(dest)n.addEventListener("dblclick",e=>{e.preventDefault();e.stopPropagation();navigate(dest.mode,dest.name)});
}
function bus(p,points,details,c=C.data,w=3,dashed=false){
  const n=add(p,elem("g"));route(n,points,"#071522",w+7,dashed?"7 5":"");route(n,points,c,w,dashed?"7 5":"");
  route(n,points,"transparent",Math.max(16,w+13));clickable(n,details);return n;
}
function card(p,x,y,w,h,label,desc,c=C.ip,details={},dest=null){
  const n=add(p,elem("g"));box(n,x,y,w,h,"#142b3e",c,9,1.5,details.planned?"5 4":"");
  box(n,x,y,4,h,c,"none",2,0);text(n,x+14,y+(h>60?30:23),clip(label,Math.max(11,Math.floor((w-22)/8.2))),h>60?15:12,C.text,720);
  if(desc)text(n,x+14,y+(h>60?51:40),clip(desc,Math.max(10,Math.floor((w-22)/7.2))),10,C.muted);
  if(dest)text(n,x+w-14,y+25,"›",21,c,700,"end");
  clickable(n,{title:details.title||label,description:desc,...details},dest);return n;
}
function frame(p,x,y,w,h,name,meta,c="#567f9c"){
  const n=add(p,elem("g"));box(n,x,y,w,h,"#0c1d2e",c,15,1.7);
  box(n,x,y,w,47,c+"20","none",15,0);route(n,[[x,y+47],[x+w,y+47]],c,1.1);
  text(n,x+19,y+30,name,17,C.text,770);text(n,x+w-17,y+29,meta,10,c,650,"end");return n;
}
function netCard(p,name,x,y,w,h){
  const q=nets.get(name);if(!q)return;
  const routers=q.instances.filter(n=>n.includes(".router_")).length,interfaces=q.instances.length-routers;
  card(p,x,y,w,h,name.includes("config")?"CONFIG NoC":"DATA NoC",routers+" routers · "+interfaces+" interfaces",color(name),
    {title:name,kind:"Real FlooNoC network",source:q.info?.source,status:q.info?.status,router_count:routers,interfaces}, {mode:"noc",name});
}
function subBox(p,name,r){
  const mem=/memory/i.test(name),s=groups.get(name+"_subsystem");
  const content=frame(p,r.x,r.y,r.w,r.h,name.toUpperCase(),mem?"MEMORY SUBSYSTEM":"COMPUTE SUBSYSTEM",mem?"#51a6c4":"#537db3");
  const local=networksOf(name).sort((a,b)=>a.includes("data")?-1:b.includes("data")?1:0);
  const blocks=g.nodes.filter(n=>memberOf.get(n.id)===name&&!networkOf(n.id));
  const kinds=["cpu","dma","sram","dma_csr","reset_ctrl","internal_target_crossbar","ctrl"];
  blocks.sort((a,b)=>{const i=kinds.indexOf(short(a.id)),j=kinds.indexOf(short(b.id));return(i<0?99:i)-(j<0?99:j)||a.id.localeCompare(b.id)});
  const top=r.y+65,netX=r.x+r.w*.55,netW=r.w*.4,blockX=r.x+17,blockW=r.w*.45;
  local.slice(0,2).forEach((net,i)=>netCard(content,net,netX,top+i*104,netW,78));
  blocks.slice(0,5).forEach((n,i)=>card(content,blockX,top+i*59,blockW,50,short(n.id),role(n),C.ip,{title:n.id,kind:"RTL IP/boundary",source:n.info?.source,status:n.info?.status,instance:n.id,actor:actorFor(n)?.label||null,actor_status:actorFor(n)?.kind||"unregistered"},ipDestination(n.id)));
  g.edges.filter(e=>{
    const a=e.from.instance,b=e.to.instance;
    return (a.startsWith(name+".")&&networkOf(b)?.startsWith(name+"_"))||(b.startsWith(name+".")&&networkOf(a)?.startsWith(name+"_"));
  }).forEach(e=>{
    const ep=e.from.instance.startsWith(name+".")?e.from.instance:e.to.instance;
    const nn=networkOf(e.from.instance.startsWith(name+".")?e.to.instance:e.from.instance);
    const i=blocks.findIndex(b=>b.id===ep),j=local.indexOf(nn);if(i<0||i>4||j<0||j>1||!(plane.value==="all"||plane.value===edgeType(e)))return;
    const y1=top+i*59+25,y2=top+j*104+39;
    bus(content,[[blockX+blockW,y1],[netX-10,y1],[netX-10,y2],[netX,y2]],
      {title:e.name||"Bus link",kind:"Generator-declared AXI/control",from:e.from,to:e.to,signals:e.signals,status:e.status},color(nn),2);
  });
  const btn=add(content,elem("g"));box(btn,r.x+r.w-171,r.y+r.h-36,153,25,"#1e405c","#5b89a7",6);
  text(btn,r.x+r.w-160,r.y+r.h-19,"Explore subsystem ›",11,"#bfe5fa",660);
  clickable(btn,{title:name,kind:"Subsystem",members:s?.instances.length}, {mode:"sub",name});
}
function fullChip(){
  const computes=subs.filter(s=>/compute/i.test(subName(s))),other=subs.filter(s=>!/compute/i.test(subName(s)));
  const loc=new Map;
  computes.forEach((s,i)=>loc.set(subName(s),{x:30,y:118+i*413,w:450,h:380}));
  other.forEach((s,i)=>loc.set(subName(s),{x:1060,y:285+i*400,w:440,h:375}));
  // Additional non-compute subsystems receive their own rows automatically.
  dims={w:1525,h:Math.max(980,...[...loc.values()].map(r=>r.y+r.h+45))};
  const all=add(svg,elem("g"));box(all,0,0,dims.w,dims.h,C.bg,"none",0);
  text(all,38,47,"SYSTEM-ON-CHIP  /  LOGICAL COMPOSITION",13,"#9dbbd2",770);
  text(all,38,78,"Local fabrics within subsystems · shared global AXI data and control networks",18,C.text,650);
  const central={x:585,y:275,w:377,h:402};
  const wiring=add(all,elem("g"));
  const summarized=new Map;
  for(const e of g.edges){
    const src=memberOf.get(e.from.instance)|| (networkOf(e.from.instance)?.startsWith("global_")?"global":null);
    const dst=memberOf.get(e.to.instance)|| (networkOf(e.to.instance)?.startsWith("global_")?"global":null);
    if(!src||!dst||src===dst)continue;
    const typ=edgeType(e),key=src+"|"+dst+"|"+typ;
    if(!summarized.has(key))summarized.set(key,{a:src,b:dst,type:typ,edges:[]});
    summarized.get(key).edges.push(e);
  }
  for(const p of summarized.values()){
    if(plane.value!=="all"&&plane.value!==p.type)continue;
    const a=p.a==="global"?central:loc.get(p.a),b=p.b==="global"?central:loc.get(p.b);if(!a||!b)continue;
    const fromRight=a.x<b.x,x1=fromRight?a.x+a.w:a.x,x2=fromRight?b.x:b.x+b.w;
    const y1=a.y+(p.type==="data"?155:265),y2=b.y+(p.type==="data"?155:265),xm=(x1+x2)/2;
    bus(wiring,[[x1,y1],[xm,y1],[xm,y2],[x2,y2]],{title:p.a+" ⇄ "+p.b,kind:p.type.toUpperCase()+" bus",count:p.edges.length,links:p.edges.map(e=>({from:e.from,to:e.to,status:e.status,signals:e.signals}))},p.type==="data"?C.data:C.config,3.7);
  }
  const core=frame(all,central.x,central.y,central.w,central.h,"GLOBAL FABRIC","SHARED INTERCONNECT","#4a9abb");
  [...nets.keys()].filter(n=>n.startsWith("global_")).sort((a,b)=>a.includes("data")?-1:1).forEach((n,i)=>netCard(core,n,central.x+20,central.y+78+i*134,central.w-40,103));
  for(const s of subs)subBox(all,subName(s),loc.get(subName(s)));
  text(all,38,dims.h-29,"Generated structural topology · selected test profile can replace active RTL with verification actors",11,C.muted);
  return {label:"Full chip",count:subs.length+" subsystems · "+nets.size+" NoCs"};
}
function subsystem(name){
  const s=groups.get(name+"_subsystem");if(!s)return fullChip();
  const blocks=g.nodes.filter(n=>memberOf.get(n.id)===name&&!networkOf(n.id));
  const netNames=networksOf(name);
  dims={w:1320,h:Math.max(655,200+blocks.length*95,185+netNames.length*155)};
  const root=add(svg,elem("g"));box(root,0,0,dims.w,dims.h,C.bg,"none",0);
  text(root,40,47,name.toUpperCase()+"  /  SUBSYSTEM COMPOSITION",17,C.text,740);
  text(root,40,76,"IP blocks, memory / reset endpoints, local NoCs, and shared external fabrics",13,C.muted);
  const lpos=new Map,npos=new Map,xpos=new Map,top=147;
  text(root,35,top-20,"RTL IP / MODELS",12,"#91b3cd",700);
  text(root,520,top-20,"LOCAL FABRICS",12,"#91b3cd",700);
  text(root,1025,top-20,"EXTERNAL LINKS",12,"#91b3cd",700);
  const wires=add(root,elem("g")),draw=add(root,elem("g"));
  blocks.sort((a,b)=>a.id.localeCompare(b.id));
  blocks.forEach((b,i)=>{const l={x:35,y:top+i*91,w:330,h:64};lpos.set(b.id,l);
    card(draw,l.x,l.y,l.w,l.h,short(b.id),role(b),C.ip,{title:b.id,kind:"RTL IP/boundary",instance:b.id,status:b.info?.status,source:b.info?.source},ipDestination(b.id))});
  netNames.forEach((name,i)=>{const l={x:520,y:top+i*155,w:350,h:112};npos.set(name,l);netCard(draw,name,l.x,l.y,l.w,l.h)});
  const outside=g.edges.filter(e=>{
    const a=memberOf.get(e.from.instance),b=memberOf.get(e.to.instance);
    return (a===name&&b!==name)||(b===name&&a!==name);
  });
  const external=[...new Set(outside.map(e=>{
    const target=memberOf.get(e.from.instance)===name?e.to.instance:e.from.instance;
    return networkOf(target)?.startsWith("global_")?networkOf(target):memberOf.get(target)||target;
  }))].filter(k=>!k.startsWith(name+"_")).slice(0,8);
  external.forEach((id,i)=>{const l={x:1025,y:top+i*86,w:255,h:61};xpos.set(id,l);
    card(draw,l.x,l.y,l.w,l.h,id.replace(/_/g," "),id.startsWith("global")?"Shared NoC":"External component",color(id),
      {title:id,kind:"External link"},nets.has(id)?{mode:"noc",name:id}:null)});
  const seen=new Set;
  for(const e of g.edges){
    const src=e.from.instance,dst=e.to.instance;
    const ep=lpos.has(src)?src:lpos.has(dst)?dst:null,other=ep===src?dst:src;
    const local=networkOf(other);
    if(ep&&npos.has(local)&&(plane.value==="all"||plane.value===edgeType(e))){
      const a=lpos.get(ep),b=npos.get(local),key=ep+"|"+local;if(seen.has(key))continue;seen.add(key);
      const y=a.y+a.h/2,yy=b.y+b.h/2;
      bus(wires,[[a.x+a.w,y],[450,y],[450,yy],[b.x,yy]],
        {title:e.name,kind:"Declared intra-subsystem link",from:e.from,to:e.to,status:e.status,signals:e.signals},color(local),2.8);
    }
  }
  for(const e of outside){
    const mine=memberOf.get(e.from.instance)===name?e.from.instance:e.to.instance;
    const other=mine===e.from.instance?e.to.instance:e.from.instance,local=networkOf(mine);
    const global=networkOf(other)?.startsWith("global_")?networkOf(other):memberOf.get(other)||other;
    if(!local||!npos.has(local)||!xpos.has(global)||(plane.value!=="all"&&plane.value!==edgeType(e)))continue;
    const key=local+"|"+global;if(seen.has(key))continue;seen.add(key);
    const a=npos.get(local),b=xpos.get(global),y=a.y+a.h/2,yy=b.y+b.h/2;
    bus(wires,[[a.x+a.w,y],[943,y],[943,yy],[b.x,yy]],
      {title:local+" ⇄ "+global,kind:"Inter-subsystem bus",from:e.from,to:e.to,status:e.status,signals:e.signals},color(local),3.2);
  }
  text(root,35,dims.h-30,"Click a NoC to inspect its generated XY router grid and attached NIs.",12,C.muted);
  return {label:name,count:blocks.length+" IPs · "+netNames.length+" local networks"};
}
function ipView(id){
  const selected=nodes.get(id);
  const moduleName=ipModule(id);
  const m=moduleName?parsedModules.get(moduleName):null;
  const children=m?.instances||[];
  const shown=Math.min(children.length,22);
  dims={w:1160,h:Math.max(500,245+shown*75)};
  const root=add(svg,elem("g"));box(root,0,0,dims.w,dims.h,C.bg,"none",0);
  text(root,38,47,id.toUpperCase()+" / IP COMPOSITION",17,C.text,760);
  text(root,38,79,(selected?.info?.ip||"RTL boundary")+" · "+(selected?.info?.status||"status not specified"),13,C.muted);
  text(root,38,108,"Selected profile "+profile.value+" · custom RTL hierarchy is a syntax parse, not proof this variant elaborates it",12,C.planned);
  if(trafficSourcesFor(id).length){
    text(root,40,137,"Verified protocol observations: select this IP to inspect run-specific link traffic",12,C.data,650);
  }
  if(!m){
    card(root,40,153,1050,82,id,"No parsed implementation in the canonical checked-in RTL source",C.ip,{title:id,kind:"opaque / reserved IP boundary"});
    text(root,42,276,"Pinned upstream IP or opt-in variant may be external. No internal wiring is inferred.",12,C.muted);
    return {label:id,count:"Opaque boundary · no verified internal hierarchy"};
  }
  card(root,40,153,435,70,moduleName,m.source||"Parsed module",C.ip,
       {title:moduleName,kind:"slang CST parsed RTL module",source:m.source,evidence:m.evidence});
  text(root,543,142,children.length+" parsed child instantiations",13,C.muted,650);
  children.slice(0,22).forEach((inst,i)=>{
    const y=163+i*75,more=parsedModules.has(inst.module)&&inst.module!==moduleName;
    route(root,[[475,188],[510,188],[510,y+30],[537,y+30]],more?C.data:C.planned,2);
    card(root,537,y,560,62,inst.name,inst.module+(more?" · open child":" · leaf / external"),more?C.data:C.planned,
      {title:inst.name,kind:"Parsed instance",rtl_module:inst.module,source:inst.source,port_count:inst.port_count,
       conditional_generate:inst.conditional_generate,evidence:inst.evidence},
      more?{mode:"module",name:inst.module}:null);
  });
  if(children.length>22)text(root,41,dims.h-26,(children.length-22)+" more instances are in the compiler-parsed RTL table",12,C.muted);
  else text(root,41,dims.h-26,"Parsed module composition is not elaborated or runtime-tested connectivity.",12,C.muted);
  return {label:id,count:children.length+" parsed child instances · "+moduleName};
}
function moduleView(name){
  const m=parsedModules.get(name);
  if(!m)return {label:name,count:"No parsed module available"};
  const children=m.instances||[];
  dims={w:1120,h:Math.max(460,215+Math.min(children.length,22)*73)};
  const root=add(svg,elem("g"));box(root,0,0,dims.w,dims.h,C.bg,"none",0);
  text(root,38,47,name.toUpperCase()+" / RTL MODULE",17,C.text,750);
  text(root,38,80,m.source+" · syntax parsed (not elaborated)",12,C.muted);
  children.slice(0,22).forEach((inst,i)=>{
    const more=parsedModules.has(inst.module)&&inst.module!==name;
    card(root,45,120+i*73,1030,59,inst.name,inst.module+(more?" · open child":" · leaf / external"),
      more?C.data:C.planned,{title:inst.name,kind:"Parsed instance",source:inst.source,port_count:inst.port_count},
      more?{mode:"module",name:inst.module}:null);
  });
  if(!children.length)text(root,43,162,"No nested RTL module instances parsed for this source.",13,C.muted);
  return {label:name,count:children.length+" parsed child instances"};
}
function network(name){
  const group=nets.get(name);if(!group)return fullChip();
  const router=new Map;let mx=0,my=0;
  for(const id of group.instances){
    const m=id.match(/\.router_(\d+)_(\d+)$/);if(!m)continue;
    const x=+m[1],y=+m[2];router.set(id,[x,y]);mx=Math.max(mx,x);my=Math.max(my,y);
  }
  const cellW=305,cellH=248,x0=70,y0=145;
  dims={w:Math.max(850,x0*2+(mx+1)*cellW),h:Math.max(665,y0+(my+1)*cellH+65)};
  const root=add(svg,elem("g"));box(root,0,0,dims.w,dims.h,C.bg,"none",0);
  const clr=color(name);
  text(root,40,46,name.replace(/_/g," ").toUpperCase()+"  /  FLOONOC ROUTERS",17,C.text,750);
  text(root,40,76,router.size+" routers  ·  "+(group.instances.length-router.size)+" AXI network interfaces  ·  "+(mx+1)+" × "+(my+1)+" generated mesh",13,C.muted);
  text(root,40,105,"X/Y positions and NI attachments derived from generated FlooGen topology, not a decorative arrangement",11,clr,650);
  const coords=new Map;
  router.forEach(([x,y],id)=>coords.set(id,{x:x0+x*cellW+cellW/2,y:y0+y*cellH+65}));
  const wires=add(root,elem("g")),tiles=add(root,elem("g"));
  const edges=g.edges.filter(e=>group.instances.includes(e.from.instance)&&group.instances.includes(e.to.instance));
  for(const e of edges){
    if(!router.has(e.from.instance)||!router.has(e.to.instance))continue;
    const a=coords.get(e.from.instance),b=coords.get(e.to.instance);
    const hor=a.x!==b.x,aa=[a.x+(hor?(b.x>a.x?44:-44):0),a.y+(hor?0:(b.y>a.y?31:-31))];
    const bb=[b.x-(hor?(b.x>a.x?44:-44):0),b.y-(hor?0:(b.y>a.y?31:-31))];
    bus(wires,[aa,bb],{title:e.name,kind:"FlooNoC router-to-router link",from:e.from,to:e.to,status:e.status},clr,5);
  }
  router.forEach(([x,y],id)=>{
    const p=coords.get(id),b=add(tiles,elem("g"));
    box(b,p.x-45,p.y-32,90,64,"#17394b",clr,9,2.3);
    text(b,p.x,p.y-3,"ROUTER",10,C.muted,700,"middle");
    text(b,p.x,p.y+20,x+", "+y,16,C.text,780,"middle");
    clickable(b,{title:id,kind:"Router",position:[x,y],source:group.info?.source,status:group.info?.status});
  });
  const assigned=new Map;
  for(const e of edges){
    const a=router.has(e.from.instance)?e.from.instance:router.has(e.to.instance)?e.to.instance:null;
    const b=a===e.from.instance?e.to.instance:e.from.instance;
    if(!a||!b||router.has(b))continue;
    if(!assigned.has(a))assigned.set(a,[]);assigned.get(a).push({id:b,edge:e});
  }
  for(const [rid,list] of assigned){
    list.sort((a,b)=>a.id.localeCompare(b.id));
    const p=coords.get(rid);
    list.forEach((item,i)=>{
      const x=p.x-97,y=p.y+51+i*40;
      bus(wires,[[p.x,p.y+32],[p.x,y]],{title:item.edge.name,kind:"NI-to-router link",from:item.edge.from,to:item.edge.to,status:item.edge.status},clr,1.7);
      const metadata=nodes.get(item.id);
      card(tiles,x,y,195,32,short(item.id),"",clr,{title:item.id,kind:"AXI network interface",instance:item.id,role:metadata?.info?.role,protocol:metadata?.info?.protocol,data_bits:metadata?.info?.data_bits,source:group.info?.source});
    });
  }
  text(root,40,dims.h-29,edges.length+" real generated structural edges · select a link to inspect source/destination router ports.",12,C.muted);
  return {label:name,count:router.size+" routers · "+(group.instances.length-router.size)+" interfaces"};
}

const trafficHost=document.getElementById("arch-link-traffic");
const trafficRun=document.getElementById("arch-traffic-run");
const trafficSource=document.getElementById("arch-traffic-source");
const trafficRows=document.getElementById("arch-traffic-rows");
const trafficActions=document.getElementById("arch-traffic-actions");
const trafficCount=document.getElementById("arch-traffic-count");
const trafficContext=document.getElementById("arch-traffic-context");

// Source-to-IP ownership is structural/name-based, not a claim of active
// electrical connectivity. Unknown source IDs remain accessible through
// test-run reports rather than being attached to an invented diagram node.
function trafficOwner(source){
  // Bind to the deepest *real* architecture node owning this monitor.
  // memory0.ddr0.dfi -> memory0.ddr0, including nested IPs and adapters.
  // Do not assign a name-only pseudo-node; exact source ownership is
  // matched against generator-derived instances, not invented RTL links.
  const name=String(source);
  let owner=null;
  for(const id of nodes.keys()){
    if((name===id||name.startsWith(id+"."))&&
       (owner===null||id.length>owner.length))owner=id;
  }
  if(owner)return owner;
  // Some external interface probes are adjacent to the IP rather than
  // module children: pcie0.rx_req or ethernet0.gmii_tx -> pcie0.ip etc.
  const base=name.split(".")[0];
  if(nodes.has(base+".ip"))return base+".ip";
  if(nodes.has(base))return base;
  return null;
}
const trafficSourcesFor=owner=>linkRuns.flatMap(run=>(run.links?.sources||[])
  .filter(source=>trafficOwner(source.source)===owner));
function trafficRunsFor(owner){
  return linkRuns.filter(run=>(run.links?.sources||[])
    .some(source=>trafficOwner(source.source)===owner));
}
function trafficOption(select,value,label){
  const o=document.createElement("option");o.value=value;o.textContent=label;select.append(o);
}
function trafficCell(tr,value){
  const td=document.createElement("td");
  td.textContent=String(value??"—");tr.append(td);
}
function trafficLink(label,url){
  const a=document.createElement("a");a.textContent=label;
  a.href=url;a.rel="noopener";return a;
}
function trafficRender(){
  const owner=trafficHost.dataset.owner;
  const runs=trafficRunsFor(owner);
  const run=runs.find(x=>String(x.run_id)+"-"+String(x.attempt)===trafficRun.value)||runs[0];
  trafficSource.replaceChildren();trafficRows.replaceChildren();trafficActions.replaceChildren();
  if(!run)return;
  const sources=run.links.sources.filter(s=>trafficOwner(s.source)===owner);
  for(const s of sources)trafficOption(trafficSource,s.source,s.source+" · "+s.protocol+" · "+s.count+" observations");
  trafficSource.value=sources.some(s=>s.source===trafficSource.dataset.preferred)
    ?trafficSource.dataset.preferred:(sources[0]?.source||"");
  trafficDisplaySource(run);
}
function trafficDisplaySource(run){
  const owner=trafficHost.dataset.owner;
  const source=run.links.sources.find(s=>s.source===trafficSource.value&&trafficOwner(s.source)===owner);
  trafficRows.replaceChildren();trafficActions.replaceChildren();
  if(!source)return;
  trafficSource.dataset.preferred=source.source;
  trafficCount.textContent=source.count+" observed "+source.protocol+" records · "+
    Object.entries(source.operations).map(([k,v])=>k+": "+v).join(" · ") +
    (run.links.capture_complete?" · capture complete":" · incomplete capture");
  trafficContext.textContent="Source-verified "+run.target+" · "+run.workflow+" #"+run.run_id+
    " · tested "+run.source_sha.slice(0,12)+
    " · "+source.implementation+" · "+source.clock_domain;
  for(const record of source.preview){
    const tr=document.createElement("tr");
    const fmt=record.fields||{};
    const ns=record.end_ps??record.start_ps;
    trafficCell(tr,typeof ns==="number"?(ns/1000).toFixed(3):"—");
    trafficCell(tr,source.source);
    trafficCell(tr,record.operation);
    trafficCell(tr,record.id||fmt.tag||"—");
    trafficCell(tr,JSON.stringify(fmt));
    trafficRows.append(tr);
  }
  if(!source.preview.length){
    const tr=document.createElement("tr");
    const td=document.createElement("td");td.colSpan=5;
    td.textContent="No preview records in this monitor";tr.append(td);trafficRows.append(tr);
  }
  const query=new URLSearchParams({protocol:source.protocol,source:source.source});
  trafficActions.append(
    trafficLink("Inspect traffic on Test Runs",
      "runs.html?run="+encodeURIComponent(run.run_id+"-"+run.attempt+"/"+run.target)+
      "&"+query.toString()),
    trafficLink("Raw verified capture JSON",run.raw_path),
    trafficLink("AXI / NoC correlated report",run.axi_report_path)
  );
}
function inspectTraffic(item){
  const owner=item.traffic_owner||item.instance||item.title;
  const runs=trafficRunsFor(owner);
  trafficHost.hidden=!runs.length;
  if(!runs.length)return;
  trafficHost.dataset.owner=owner;
  trafficRun.replaceChildren();
  for(const run of runs)trafficOption(trafficRun,String(run.run_id)+"-"+String(run.attempt),
    run.target+" · "+run.recorded_at+" · "+run.source_sha.slice(0,10));
  trafficRun.onchange=()=>{trafficSource.dataset.preferred="";trafficRender()};
  trafficSource.onchange=()=>trafficDisplaySource(
    runs.find(x=>String(x.run_id)+"-"+String(x.attempt)===trafficRun.value)||runs[0]);
  trafficSource.dataset.preferred="";
  trafficRender();
}

function inspect(item,dest){
  next=dest||null;title.textContent=item.title||"Selected";subtitle.textContent=item.description||item.kind||"";
  facts.replaceChildren();const dl=document.createElement("dl");
  for(const [k,v] of Object.entries(item)){
    if(["title","description","kind"].includes(k)||v==null)continue;
    const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=k.replace(/_/g," ");
    dd.textContent=typeof v==="object"?JSON.stringify(v):String(v);dl.append(dt,dd);
  }
  facts.append(dl);document.getElementById("arch-inspect-links").replaceChildren();
  const id=item.instance||item.title;
  const rtlMatch=rtlModules.flatMap(m=>(m.instances||[]).map(inst=>({parent:m.name,...inst})))
     .find(inst=>inst.name===id||inst.module===id);
  if(rtlMatch){
    const element=document.createElement("div");
    element.className="arch-chip";
    element.textContent="slang CST: "+rtlMatch.module+" "+rtlMatch.name+" ("+rtlMatch.port_count+" ports)";
    facts.append(element);
  }
  const sourceNode=nodes.get(item.instance||item.title);
  const memContract=sourceNode?.info?.memory_integration;
  if(memContract){
    const label=document.createElement("p");
    label.className="muted";
    label.textContent="SoC implementation: "+memContract.soc_backend+
       " · configured controller profile: "+(memContract.controller_profile||"none")+
       " (configuration is not physical controller integration)";
    facts.append(label);
  }
  const ep=inventory.endpoints[item.instance||item.title];
  if(ep){const b=document.createElement("button");b.textContent="Inspect "+ep.signals.length+" RTL signal ports";b.addEventListener("click",()=>pickEndpoint(item.instance||item.title));document.getElementById("arch-inspect-links").append(b)}
  inspectTraffic(item);
  open.hidden=!next;
  if(next)open.textContent="Open "+(next.mode==="sub"?"subsystem":next.mode==="noc"?"NoC":"RTL module")+" ›";
}
open.addEventListener("click",()=>{if(next)navigate(next.mode,next.name)});
function resize(){
  svg.setAttribute("viewBox","0 0 "+dims.w+" "+dims.h);
  svg.setAttribute("width",Math.ceil(dims.w*zoom));svg.setAttribute("height",Math.ceil(dims.h*zoom));
  svg.style.width=Math.ceil(dims.w*zoom)+"px";svg.style.height=Math.ceil(dims.h*zoom)+"px";
}
function fit(){zoom=Math.max(.30,Math.min(1.2,(vp.clientWidth-12)/dims.w,(vp.clientHeight-12)/dims.h));resize()}
function navigate(kind,name){
  current=kind;scope=name||"";svg.replaceChildren();crumbs.replaceChildren();
  const trail=[["Full chip","chip",""]];
  if(kind==="sub")trail.push([name,"sub",name]);
  if(kind==="ip"){
    const sub=subs.find(q=>name.startsWith(subName(q)+"."));
    if(sub)trail.push([subName(sub),"sub",subName(sub)]);
    trail.push([name,"ip",name]);
  }
  if(kind==="module")trail.push([name,"module",name]);
  if(kind==="noc"){
    const sub=subs.find(q=>name.startsWith(subName(q)+"_"));if(sub)trail.push([subName(sub),"sub",subName(sub)]);
    trail.push([name,"noc",name]);
  }
  trail.forEach(([label,type,id],i)=>{
    if(i){const slash=document.createElement("span");slash.textContent="/";crumbs.append(slash)}
    const btn=document.createElement("button");btn.textContent=label;
    if(i===trail.length-1)btn.setAttribute("aria-current","page");
    btn.addEventListener("click",()=>navigate(type,id));crumbs.append(btn);
  });
  const summary=kind==="noc"?network(name):kind==="sub"?subsystem(name):kind==="ip"?ipView(name):kind==="module"?moduleView(name):fullChip();
  inspect({title:summary.label,kind:kind==="chip"?"System overview":kind==="sub"?"Subsystem view":kind==="noc"?"Generated NoC mesh":"Compiler-parsed RTL composition",description:summary.count,...(kind==="ip"?{instance:name,traffic_owner:name}:{})});
  status.textContent=summary.count+" · "+(kind==="noc"?"Generated router topology":"Subsystem hierarchy");
  requestAnimationFrame(()=>{fit();vp.scrollTo(0,0)});
}
document.getElementById("arch-fit").addEventListener("click",fit);
document.getElementById("arch-zoom-in").addEventListener("click",()=>{zoom=Math.min(3.5,zoom*1.25);resize()});
document.getElementById("arch-zoom-out").addEventListener("click",()=>{zoom=Math.max(.25,zoom/1.25);resize()});
document.getElementById("arch-export").addEventListener("click",()=>{
  const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:"image/svg+xml;charset=utf-8"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=(current==="chip"?"soc-full-chip":scope.replace(/[^A-Za-z0-9_-]/g,"_"))+".svg";
  document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
plane.addEventListener("change",()=>navigate(current,scope));
Object.keys(g.profiles).forEach(n=>{const o=document.createElement("option");o.value=n;o.textContent=n;profile.append(o)});
profile.value=g.profiles["chip-dma"]?"chip-dma":Object.keys(g.profiles)[0];
profile.addEventListener("change",()=>{
  navigate(current,scope);
  const p=g.profiles[profile.value],count=Object.keys(p.actors||{}).length;
  status.textContent="Test profile "+profile.value+" · "+(p.actor_catalog_status==="runtime_generated_not_available"?"run-generated actor manifest unavailable; composition is not execution proof":count+" declared actor roles · no runtime activity claimed");
});
const es=document.getElementById("ex-endpoint"),bs=document.getElementById("ex-bus"),fil=document.getElementById("ex-signal-filter"),tb=document.getElementById("ex-signal-rows"),lt=document.getElementById("ex-connection-rows");
const sourceBase=(document.querySelector("footer a")?.href||"").replace("/tree/","/blob/").replace(/\/$/,"");
const option=(s,v,l)=>{const o=document.createElement("option");o.value=v;o.textContent=l;s.append(o)};
option(es,"__unbound__","Top-level clocks / resets");Object.keys(inventory.endpoints).sort().forEach(k=>option(es,k,k));
const cell=(tr,v,url)=>{const td=document.createElement("td"),n=document.createElement(url?"a":"span");n.textContent=String(v);if(url)n.href=url;td.append(n);tr.append(td)};
function busOptions(){
  const ep=inventory.endpoints[es.value];bs.replaceChildren();option(bs,"all","All bus channels");
  for(const k of Object.keys(ep?.protocols||{}).sort())option(bs,k,k);
  renderSignals();
}
function renderSignals(){
  const ep=inventory.endpoints[es.value],search=fil.value.toLowerCase();
  const rows=(ep?.signals||inventory.unbound_ports||[]).filter(p=>(bs.value==="all"||p.protocol+":"+p.interface===bs.value)&&(!search||(p.name+" "+p.channel).toLowerCase().includes(search)));
  tb.replaceChildren();lt.replaceChildren();
  rows.forEach(p=>{
    const tr=document.createElement("tr"),m=(p.location||"").match(/^(.*):(\d+):(\d+)$/);
    cell(tr,p.name);cell(tr,p.channel);cell(tr,p.width);cell(tr,p.direction);
    cell(tr,p.location||"",m&&sourceBase?sourceBase+"/"+m[1]+"#L"+m[2]:null);tb.append(tr);
  });
  const links=inventory.declared_connections.filter(e=>e.from.instance===es.value||e.to.instance===es.value);
  links.forEach(e=>{const tr=document.createElement("tr");
    cell(tr,e.from.instance+"."+e.from.port);cell(tr,e.to.instance+"."+e.to.port);
    cell(tr,(e.declared_signals||[]).map(s=>s.name).join(", ")||e.link_type);cell(tr,e.status+" (declared)");lt.append(tr);
  });
  if(!rows.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=5;td.textContent="No matching signals";tr.append(td);tb.append(tr)}
  if(!links.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=4;td.textContent="No declared links";tr.append(td);lt.append(tr)}
  document.getElementById("arch-signals-count").textContent="· "+inventory.counts.ports+" ports";
  document.getElementById("ex-signal-status").textContent=rows.length+" real RTL ports · protocol grouping inferred from names; links declared by generator";
}
function pickEndpoint(id){if(!inventory.endpoints[id])return;es.value=id;busOptions();const details=document.getElementById("arch-signals");details.open=true;details.scrollIntoView({behavior:"smooth",block:"start"})}
es.addEventListener("change",busOptions);bs.addEventListener("change",renderSignals);fil.addEventListener("input",renderSignals);
// Compiler-derived instance and port bindings are a separate evidence
// channel from the FlooGen topology; neither is silently substituted.
const rtlRows=document.getElementById("arch-rtl-rows"),
      rtlCount=document.getElementById("arch-rtl-count"),
      rtlStatus=document.getElementById("arch-rtl-validation");
const rtlModules=parsed.modules||[];
rtlCount.textContent=parsed.evidence==="compiler_parse_not_run"
  ?" · parser not run"
  :" · "+(parsed.summary?.instances||0)+" RTL instances";
const c=parsed.fabric_contract||{};
rtlStatus.textContent=parsed.evidence==="compiler_parse_not_run"
  ?"Compiler parse evidence not supplied in this local preview"
  :(c.independent_planes
    ?"slang CST: all "+(c.resolved_networks?.length||0)+" generated data/config NoCs found as separate RTL instances"
    :"slang CST: independent NoC validation unavailable");
for(const m of rtlModules){
  for(const inst of m.instances||[]){
    const tr=document.createElement("tr");
    cell(tr,m.name);cell(tr,inst.name);cell(tr,inst.module);
    const bindings=(inst.ports||[]).map(p=>p.port+" = "+p.expression).join("; ");
    cell(tr,bindings||"(no named bindings)");
    rtlRows.append(tr);
  }
}
busOptions();navigate("chip","");
})();