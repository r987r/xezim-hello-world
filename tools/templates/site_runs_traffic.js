(() => {
"use strict";
// Shared, protocol-neutral renderer. No hard-coded PCIe/Ethernet/APB/AXI5
// decoder. The previously validated ProtocolTrace schema owns the data.
const D=JSON.parse(document.getElementById("site-data").textContent);
const $=id=>document.getElementById(id);
const current={
  entry:null,all:[],filtered:[],preview:true,request:0,page:0,
  cache:new Map(),size:100
};
const candidates=D.entries.filter(e=>e.protocol_links?.sources?.length||e.protocols?.length);
const label=e=>e.target+" · CI #"+e.run_id+"."+e.attempt+" · "+e.source_sha.slice(0,9);
const key=e=>e.run_id+"-"+e.attempt+"/"+e.target;
const selectedRun=$("traffic-run");
const selectors={
  protocol:$("traffic-protocol"),source:$("traffic-source"),
  operation:$("traffic-operation"),state:$("traffic-state")
};
const uiText=(tag,value)=>{
  const node=document.createElement(tag);node.textContent=String(value??"");return node;
};
const option=(select,value,desc)=>{
  const o=document.createElement("option");o.value=value;o.textContent=desc;select.append(o);
};
const unique=rows=>[...new Set(rows.filter(Boolean))].sort();
const psTime=ps=>typeof ps==="number"?(ps/1000).toLocaleString(undefined,{maximumFractionDigits:3}):"—";
const hasCapture=e=>e.protocol_links?.sources?.length||e.protocols?.length;
function listOptions(select,values,allLabel,previous){
  select.replaceChildren();option(select,"",allLabel);
  for(const value of values)option(select,value,value);
  select.value=values.includes(previous)?previous:"";
}
function init(){
  for(const e of candidates)option(selectedRun,key(e),label(e));
  if(!candidates.length){
    $("traffic-notice").textContent="No source-verified protocol observations have been published yet. Configured tests and CI results remain visible below.";
    return;
  }
  selectedRun.onchange=()=>load();
  for(const [name,node] of Object.entries(selectors)){
    node.onchange=()=>{
      if(name==="protocol")refreshSources();
      else if(name==="source")refreshOperations();
      else apply();
    };
  }
  $("traffic-query").oninput=apply;
  $("traffic-prev").onclick=()=>{if(current.page>0){current.page--;render()}};
  $("traffic-next").onclick=()=>{if((current.page+1)*current.size<current.filtered.length){current.page++;render()}};
  $("traffic-csv").onclick=()=>exportFiltered("csv");
  $("traffic-json").onclick=()=>exportFiltered("json");
  $("traffic-open-raw").onclick=()=>{if(current.entry)window.open(rawPath(current.entry),"_blank","noopener")};
  const query=new URLSearchParams(location.search);
  const wanted=query.get("run")||query.get("test");
  if(wanted){
    const match=candidates.find(e=>key(e)===wanted||e.target===wanted||
      String(e.run_id)===wanted);
    if(match)selectedRun.value=key(match);
  }
  if(!selectedRun.value)selectedRun.selectedIndex=0;
  load({protocol:query.get("protocol"),source:query.get("source")});
}
function rawPath(e){
  return e.path.slice(0,e.path.lastIndexOf("/"))+"/protocol-transactions.json";
}
function preview(e){
  const records=[];
  for(const s of e.protocol_links?.sources||[]){
    for(const r of s.preview||[]){
      records.push({...r,source:s.source,protocol:s.protocol});
    }
  }
  return records.sort((a,b)=>(a.start_ps??0)-(b.start_ps??0));
}
async function load(initial={}){
  const id=++current.request;
  const entry=candidates.find(e=>key(e)===selectedRun.value);
  if(!entry)return;
  current.entry=entry;current.all=preview(entry);current.preview=true;
  $("traffic-provenance").textContent=
    entry.target+" · tested "+entry.source_sha+" · CI run #"+entry.run_id+
    " attempt "+entry.attempt+" · "+entry.workflow+
    " · "+(entry.passed?"target PASS":"target NOT PASS");
  $("traffic-notice").textContent="Loading full recorded protocol evidence; bounded previews are available.";
  refreshProtocols(initial);
  const path=rawPath(entry);
  try{
    let records=current.cache.get(key(entry));
    if(!records){
      const response=await fetch(path);
      if(!response.ok)throw Error("HTTP "+response.status);
      const payload=await response.json();
      if(payload.schema_version!==1||!Array.isArray(payload.records)||
         !Array.isArray(payload.sources)||payload.run?.target!==entry.target)
        throw Error("invalid protocol evidence");
      const ids=new Map(payload.sources.map(s=>[s.id,s.protocol]));
      if(payload.records.some(r=>ids.get(r.source)!==r.protocol))
        throw Error("source/protocol mismatch");
      records=payload.records;
      current.cache.set(key(entry),records);
    }
    if(id!==current.request)return;
    current.all=records;current.preview=false;
    $("traffic-notice").textContent="Showing full, source-verified protocol capture. Select a row to inspect every native field and timestamp.";
    refreshProtocols(initial);
  }catch(error){
    if(id!==current.request)return;
    $("traffic-notice").textContent="Full capture unavailable ("+error.message+
      "). Showing bounded verified preview only; counts below reflect displayed records, not all recorded observations.";
    apply();
  }
}
function refreshProtocols(initial={}){
  const old=initial.protocol??selectors.protocol.value;
  listOptions(selectors.protocol,unique(current.all.map(r=>r.protocol)),"All protocols",old);
  refreshSources(initial.source);
}
function refreshSources(preferred){
  const records=current.all.filter(r=>!selectors.protocol.value||
    r.protocol===selectors.protocol.value);
  listOptions(selectors.source,unique(records.map(r=>r.source)),"All monitors",
    preferred??selectors.source.value);
  refreshOperations();
}
function refreshOperations(){
  const records=current.all.filter(r=>
    (!selectors.protocol.value||r.protocol===selectors.protocol.value)&&
    (!selectors.source.value||r.source===selectors.source.value));
  listOptions(selectors.operation,unique(records.map(r=>r.operation)),
    "All operations",selectors.operation.value);
  apply();
}
function apply(){
  const query=$("traffic-query").value.toLowerCase().trim();
  current.filtered=current.all.filter(r=>
    (!selectors.protocol.value||r.protocol===selectors.protocol.value)&&
    (!selectors.source.value||r.source===selectors.source.value)&&
    (!selectors.operation.value||r.operation===selectors.operation.value)&&
    (!selectors.state.value||r.status===selectors.state.value)&&
    (!query||[r.source,r.protocol,r.operation,r.id,JSON.stringify(r.fields)]
      .join(" ").toLowerCase().includes(query)));
  current.page=0;render();
}
const preferred=["direction","address","requester_id","tag","length_dw",
  "dst_mac","src_mac","ether_type","src_ip","dst_ip","src_port","dst_port",
  "length_bytes","fcs_valid","completion_status","byte_count","payload_bytes"];
function fieldKeys(){
  const counts=new Map();
  for(const r of current.filtered.slice(0,500))
    for(const k of Object.keys(r.fields||{}))counts.set(k,(counts.get(k)||0)+1);
  return [...counts.keys()].sort((a,b)=>{
    const pa=preferred.indexOf(a),pb=preferred.indexOf(b);
    if(pa>=0||pb>=0)return (pa<0?999:pa)-(pb<0?999:pb);
    return counts.get(b)-counts.get(a)||a.localeCompare(b);
  }).slice(0,9);
}
function inspect(r){
  $("traffic-detail").textContent=JSON.stringify(r,null,2);
}
function render(){
  const tbody=$("traffic-rows");tbody.replaceChildren();
  const fields=fieldKeys(),head=$("traffic-head");head.replaceChildren();
  const hr=document.createElement("tr");
  for(const col of ["Time ns","Protocol","Monitor","Operation","ID / tag",
                    "Status",...fields]){
    const th=uiText("th",col);hr.append(th);
  }
  head.append(hr);
  const start=current.page*current.size;
  for(const r of current.filtered.slice(start,start+current.size)){
    const tr=document.createElement("tr");tr.tabIndex=0;
    const vals=[psTime(r.end_ps??r.start_ps),r.protocol,r.source,r.operation,
      r.id??"—",r.status,...fields.map(k=>r.fields?.[k]??"—")];
    for(const val of vals){
      const str=typeof val==="object"?JSON.stringify(val):String(val);
      const td=uiText("td",str.length>150?str.slice(0,147)+"…":str);
      tr.append(td);
    }
    tr.onclick=()=>inspect(r);
    tr.onkeydown=e=>{if(e.key==="Enter")inspect(r)};
    tbody.append(tr);
  }
  if(!current.filtered.length){
    const tr=document.createElement("tr");
    const td=uiText("td","No captured observations match these filters.");
    td.colSpan=6+fields.length;tr.append(td);tbody.append(tr);
  }
  $("traffic-total").textContent=current.filtered.length+" / "+current.all.length+
    (current.preview?" preview records":" observed records")+
    " · "+(start+1)+"–"+Math.min(start+current.size,current.filtered.length);
  $("traffic-prev").disabled=current.page===0;
  $("traffic-next").disabled=(current.page+1)*current.size>=current.filtered.length;
  draw();
}
function draw(){
  const canvas=$("traffic-timeline"),ctx=canvas.getContext("2d");
  const px=window.devicePixelRatio||1, width=Math.max(450,canvas.parentElement.clientWidth-16);
  const monitors=unique(current.filtered.map(r=>r.source));
  const height=Math.max(180,75+monitors.length*32);
  canvas.width=width*px;canvas.height=height*px;canvas.style.height=height+"px";
  ctx.setTransform(px,0,0,px,0,0);ctx.clearRect(0,0,width,height);
  ctx.font="11px system-ui";ctx.textAlign="right";
  const sample=current.filtered.filter(r=>Number.isFinite(r.end_ps??r.start_ps));
  let first=Infinity,last=-Infinity;
  for(const r of sample){
    first=Math.min(first,r.start_ps??r.end_ps??0);
    last=Math.max(last,r.end_ps??r.start_ps??0);
  }
  if(!Number.isFinite(first)){first=0;last=1000;}
  const range=Math.max(1,last-first),left=Math.min(260,Math.max(130,width*.31));
  const span=Math.max(100,width-left-18);
  monitors.forEach((name,i)=>{
    const y=38+i*32;ctx.fillStyle="#b6cce1";ctx.fillText(name.slice(0,37),left-9,y+4);
    ctx.beginPath();ctx.strokeStyle="#2f435e";ctx.moveTo(left,y);ctx.lineTo(width-12,y);ctx.stroke();
  });
  const skip=Math.max(1,Math.ceil(sample.length/4500));
  for(let i=0;i<sample.length;i+=skip){
    const r=sample[i],y=38+monitors.indexOf(r.source)*32;
    const x=left+Math.max(0,Math.min(1,((r.end_ps??r.start_ps)-first)/range))*span;
    ctx.fillStyle=r.protocol==="pcie"?"#f4c477":r.protocol==="ethernet"?"#69d2b4":"#82b5f4";
    ctx.beginPath();ctx.arc(x,y,2.7,0,Math.PI*2);ctx.fill();
  }
  ctx.textAlign="center";ctx.fillStyle="#a9b9d0";
  ctx.fillText("Simulation time: "+psTime(first)+"–"+psTime(last)+" ns",left+span/2,height-13);
}
function exportFiltered(ext){
  const blob=ext==="json"
    ?new Blob([JSON.stringify({run:current.entry?.target,
      preview:current.preview,records:current.filtered},null,2)],{type:"application/json"})
    :new Blob([["protocol","source","operation","id","start_ps","end_ps","status","fields"]
      .join(","),...current.filtered.map(r=>[
       r.protocol,r.source,r.operation,r.id,r.start_ps,r.end_ps,r.status,JSON.stringify(r.fields)]
       .map(x=>'"'+String(x??"").replaceAll('"','""')+'"').join(","))].join("\r\n")],
      {type:"text/csv"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download="traffic-"+(current.entry?.target||"run")+"."+ext;
  a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
// Used by the existing per-target list to open the integrated inspector.
window.openRunTraffic=(entry)=>{
  const candidate=candidates.find(e=>key(e)===key(entry));
  if(!candidate)return;
  selectedRun.value=key(candidate);
  load();
  $("unified-traffic").scrollIntoView({behavior:"smooth",block:"start"});
};
init();
})();
