/* Same renderer for all projects. These are FlooGen/source contracts,
 * not evidence of an elaborated active instance or observed traffic. */
function drawComposition() {
  const profiles = d.noc_profiles || {};
  const name = focus.id;
  const nocs = Object.entries(profiles);
  const sub = (d.subsystems || []).find(s => s.name === name);
  const kind = focus.kind;
  const background = () => {
    svg.replaceChildren();
    svg.append(el("rect", {width: diagramW, height: diagramH, fill: "#081522"}));
  };
  const setSize = (width, height) => {
    diagramW = Math.max(340, width);
    diagramH = Math.max(340, height);
    svg.setAttribute("width", diagramW);
    svg.setAttribute("height", diagramH);
    // Reveal the complete composition on narrow screens using document
    // scrolling rather than a clipped second 470px scroll container.
    viewport.classList.toggle("arch-h-expanded", viewport.clientWidth < 760);
    background();
  };
  const card = (x, y, w, h, title, subtitle, id, group = "ip") => {
    const g = el("g", {tabindex: "0", role: "button", "data-arch-ref": id,
      "aria-label": "Open " + title});
    g.classList.add("arch-h-svg-node");
    const color = group === "noc" ? "#2dbbb4" : group === "router" ? "#b69aff" : "#549bc1";
    g.append(el("rect", {x, y, width:w, height:h, rx:10,
      stroke:color, "stroke-width":1.6, fill:group === "noc" ? "#123c41" :
        group === "router" ? "#2a2647" : "#132d46"}));
    const maxChars = Math.max(16, Math.floor((w - 22) / 8));
    const abbrev = v => String(v).length > maxChars ?
      String(v).slice(0, maxChars - 1) + "…" : String(v);
    g.append(makeText(x+12,y+27,abbrev(title),14,"#eef7ff",700));
    g.append(makeText(x+12,y+49,abbrev(subtitle),11,"#a9bfd4"));
    g.addEventListener("click",()=>open(id));
    g.addEventListener("keydown",ev=>{
      if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();open(id);}
    });
    const tt=el("title");tt.textContent=title+" — "+subtitle;g.append(tt);
    svg.append(g);
    return {x,y,w,h};
  };
  const wire=(p,q,color="#2fd1c9")=>{
    if(!p||!q)return;
    const x1=p.x+p.w,y1=p.y+p.h/2,x2=q.x,y2=q.y+q.h/2,xm=(x1+x2)/2;
    svg.insertBefore(el("path",{d:"M"+x1+" "+y1+" H"+xm+" V"+y2+" H"+x2,
      stroke:color,fill:"none","stroke-width":2,"stroke-dasharray":"5 3"}),svg.children[1]||null);
  };
  const header=(title,subline)=>{
    // Keep long subsystem/NoC names inside the actual rendered SVG on
    // narrow screens instead of clipping the header outside the viewport.
    const maxChars = Math.max(18, Math.floor((diagramW - 42) / 12));
    const clipped = text => String(text).length > maxChars ?
      String(text).slice(0, maxChars - 1) + "…" : String(text);
    svg.append(makeText(20,36,clipped(title),17,"#edf7ff",750),
               makeText(20,61,clipped(subline),11,"#9dbbd2"));
  };
  const sourceType = s => d.subsystem_types?.[s.type] || {};
  if(kind === "subsystem" && sub) {
    const ownNocs=nocs.filter(([nm,p])=>p.path?.split("/")[0]===name ||
      nm.startsWith(name+"_local_"));
    const ownTargets=(d.memory_targets||[]).filter(x=>x.name.startsWith(name+"."));
    const ownAddr=(model.address_map?.data||[]).filter(x=>x.name.startsWith(name+"."));
    const components=[];
    if(sub.cpu)components.push({title:sub.cpu.ip||"CPU",sub:"CPU • "+sub.cpu.bus,id:"ip:"+name+":cpu"});
    const type=sourceType(sub);
    if(type.dma)components.push({title:type.dma,sub:"DMA • subsystem profile",id:"profile:"+name+":dma"});
    if(sub.ip)components.push({title:sub.ip,sub:"Peripheral controller",id:"property:"+name+":ip"});
    for(const m of ownTargets)components.push({title:m.name.split(".").pop(),sub:m.kind+" • "+m.controller,id:"memory:"+m.name});
    for(const a of ownAddr.filter(x=>x.name.endsWith(".sram")))components.push({
      title:a.name.split(".").pop(),sub:"SRAM • mapped target",id:"region:"+a.name});
    if(!components.length)components.push({title:sub.type+" subsystem",sub:"No declared CPU / peripheral IP",id:"sub:"+name});
    const narrow = viewport.clientWidth < 740;
    const rows=Math.max(components.length,ownNocs.length,1);
    const totalRows = narrow ? components.length + ownNocs.length : rows;
    const compactWidth = Math.max(340, viewport.clientWidth - 16);
    setSize(narrow ? compactWidth : 1030,
      Math.max(365, narrow ? 168 + totalRows * 85 : 115 + rows * 94));
    header(name.toUpperCase()+" / SUBSYSTEM COMPOSITION",
      "IP, memory and local FlooNoC boxes from this project");
    if (narrow) {
      const boxW = diagramW - 38;
      svg.append(makeText(19,100,"IP / MEMORY COMPONENTS",12,"#9dbbd2",680));
      components.forEach((c,i)=>card(19,113+i*85,boxW,65,c.title,c.sub,c.id));
      const y = 120 + components.length*85;
      svg.append(makeText(19,y,"LOCAL NoCs (CLICK TO OPEN)",12,"#9dbbd2",680));
      ownNocs.forEach(([nm,p],i)=>card(19,y+17+i*85,boxW,65,
        nm,p.plane+" • "+p.endpoints.length+" named NIs","noc:"+nm,"noc"));
    } else {
      svg.append(makeText(35,92,"IP / MEMORY COMPONENTS",12,"#9dbbd2",680),
                 makeText(590,92,"LOCAL NoCs (CLICK TO OPEN)",12,"#9dbbd2",680));
      const lhs=components.map((c,i)=>card(35,108+i*94,360,67,c.title,c.sub,c.id));
      const rhs=ownNocs.map(([nm,p],i)=>card(590,108+i*94,395,67,
        nm,p.plane+" • "+p.endpoints.length+" named NIs","noc:"+nm,"noc"));
      const belongs=(c,ep)=> {
        const label=String(ep.name||"").toLowerCase();
        if(c.id.includes(":cpu"))return label==="cpu";
        if(c.id.includes(":dma"))return label==="dma"||label.includes("dma");
        if(c.id.startsWith("memory:"))return label.includes("target")||label.includes("ingress");
        if(c.id.startsWith("region:"))return label==="sram";
        if(c.id.includes(":ip"))return label.includes("packet")||label.includes("host")||label.includes("controller");
        return false;
      };
      ownNocs.forEach(([nm,p],i)=>{
        components.forEach((c,j)=>{
          if(p.endpoints.some(e=>belongs(c,e)))
            wire(lhs[j],rhs[i],p.plane==="config"?"#b69aff":"#2fd1c9");
        });
      });
    }
    status.textContent = name+" • "+components.length+" declared IP/memory blocks • "+
      ownNocs.length+" local FlooNoCs • dashed desktop links are inferred from NI names, not qualified RTL wiring";
  } else if(kind==="noc" && profiles[name]) {
    const p=profiles[name],router=p.routers?.[0];
    const dims=router?.array||[1,1],nx=dims[0],ny=dims[1];
    const ni=p.endpoints||[];
    const cardW=160,step=190,routerX=250;
    setSize(Math.max(780,360+nx*step),Math.max(380,190+ny*120,160+ni.length*68));
    header(name.toUpperCase()+" / FlooNoC",
      p.plane+" • "+nx+"×"+ny+" routers • "+ni.length+" NIs • XY source profile");
    svg.append(makeText(routerX,99,"ROUTER ARRAY",12,"#a9bed7",700),
               makeText(20,99,"ATTACHED NETWORK INTERFACES",11,"#a9bed7",700));
    for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
      const ref="router:"+name+":"+x+":"+y;
      card(routerX+x*step,120+y*120,cardW,66,"router ["+x+","+y+"]",
        "XY router",ref,"router");
    }
    ni.forEach((e,i)=>{
      const rx=20,ry=115+i*68;
      card(rx,ry,210,52,e.name,e.mgr_port_protocol?"Manager NI":"Target NI",
        "endpoint:"+name+":"+e.name);
      const c=(p.connections||[]).find(x=>x.src===e.name);
      if(c?.dst_idx && c.dst_idx.length===2){
        const [x,y]=c.dst_idx,yy=120+y*120+33;
        svg.insertBefore(el("path",{d:"M230 "+(ry+26)+" H240 V"+yy+" H"+(routerX+x*step),
          fill:"none",stroke:"#2fd1c9","stroke-width":1.7}),svg.children[1]||null);
      }
    });
    status.textContent=name+" • "+ni.length+" actual FlooGen NI declarations • "+
      nx*ny+" router slots • not elaborated or tested";
  } else if(kind==="router" && profiles[focus.noc]) {
    const p=profiles[focus.noc];
    const attached=(p.connections||[]).filter(c=>Array.isArray(c.dst_idx)&&
      c.dst_idx[0]===focus.x&&c.dst_idx[1]===focus.y);
    setSize(775,Math.max(350,165+attached.length*85));
    header(focus.noc+" / router ["+focus.x+","+focus.y+"]",
      "Attached NIs based on FlooGen destination coordinates");
    if(!attached.length)svg.append(makeText(36,147,"No directly attached NI at this router position.",13,"#a9bfd4"));
    attached.forEach((c,i)=>{
      const endpoint=p.endpoints.find(e=>e.name===c.src);
      card(45,125+i*85,620,63,c.src,
        (endpoint?.mgr_port_protocol||endpoint?.sbr_port_protocol||[]).join(", ") +
        (endpoint?.addr_range ? " • mapped address target" : ""),
        "endpoint:"+focus.noc+":"+c.src);
    });
    status.textContent=focus.noc+" router ["+focus.x+","+focus.y+"] • "+attached.length+
      " NI attachments • source-only";
  } else if(kind==="endpoint" && profiles[focus.noc]) {
    const p=profiles[focus.noc],e=p.endpoints.find(e=>e.name===focus.endpoint);
    setSize(800,365);
    header(focus.endpoint+" / NI INTERFACE",
      focus.noc+" • "+p.plane+" • FlooGen endpoint contract");
    if(e){
      card(75,130,280,92,e.name,
        (e.mgr_port_protocol||e.sbr_port_protocol||[]).join(", "),
        "noc:"+focus.noc,"noc");
      const details=Object.entries(e).filter(([k])=>k!=="name");
      details.slice(0,5).forEach(([k,v],i)=>{
        svg.append(makeText(395,145+i*34,k+": "+JSON.stringify(v).slice(0,56),
          12,"#a6c7da"));
      });
    }
    status.textContent=focus.noc+" / "+focus.endpoint+" • NI declaration, not a measured signal";
  } else if(kind==="ip" && subNames.has(focus.sub)) {
    const s=(d.subsystems||[]).find(x=>x.name===focus.sub);
    const type=sourceType(s);
    const spec=focus.id==="cpu"?s.cpu:focus.id==="dma"?{
      ip:type.dma,parameters:type.dma_parameters
    }:focus.id==="ip"?{ip:s.ip}:s[focus.id]||{};
    const ownNocs=nocs.filter(([nm,p])=>p.path?.split("/")[0]===focus.sub);
    setSize(775,Math.max(340,140+ownNocs.length*82));
    header(focus.sub+" / "+focus.id.toUpperCase(),"Declared IP profile / local NoC neighbors");
    card(30,140,315,72,spec.ip||focus.id,JSON.stringify(spec).slice(0,48),
      "sub:"+focus.sub);
    ownNocs.forEach(([nm,p],i)=>card(435,110+i*82,300,65,nm,
      p.plane+" FlooNoC","noc:"+nm,"noc"));
    status.textContent="IP declared in project configuration • detailed parsed RTL hierarchy is separate evidence";
  } else {
    focus={kind:"chip"};diagramW=W;diagramH=H;
    draw();return;
  }
  fit();
}
