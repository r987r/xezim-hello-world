/* Shared, source-qualified SoC topology SVG. No project-name or fixed node assumptions. */
(() => {
  "use strict";
  const host = document.getElementById("arch-h-svg");
  if (!host) return;
  const model = JSON.parse(document.getElementById("arch-h-model").textContent);
  const d = model.design || {};
  const subNames = new Set((d.subsystems || []).map(s => s.name));
  const links = [];
  const add = (a, b, plane, name, reference) => {
    if (!a || !b || a === b) return;
    links.push({ a, b, plane, name, reference });
  };
  const networks = d.networks || {};
  for (const [name, spec] of Object.entries(networks)) {
    const plane = name.includes("config") ? "config" :
      name.includes("data") ? "data" : (spec.protocol || "").includes("lite") ? "config" : "data";
    if (Array.isArray(spec.links)) {
      for (let i = 0; i < spec.links.length; i++) {
        const edge = spec.links[i];
        if (!Array.isArray(edge.endpoints) || edge.endpoints.length !== 2) continue;
        add(edge.endpoints[0], edge.endpoints[1], plane, edge.name || name,
            "link:" + name + ":" + i);
      }
    }
    if (Array.isArray(spec.reachable_subsystems)) {
      for (const endpoint of spec.reachable_subsystems) {
        add("network:" + name, endpoint, plane, name, "network:" + name);
      }
    }
    if (Array.isArray(spec.outputs)) {
      const targets = spec.outputs.map(x => String(x.target || "").split(".")[0]).filter(x => subNames.has(x));
      for (const endpoint of subNames) add("network:" + name, endpoint, plane, name, "network:" + name);
      for (const endpoint of targets) add("network:" + name, endpoint, plane, name, "network:" + name);
    }
  }
  const seen = new Set();
  const edges = links.filter(e => {
    const k = [e.a, e.b].sort().join("|") + "|" + e.plane;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  const names = [...subNames];
  const graphNodes = names.map(name => ({ id: name, label: name, kind: "subsystem", ref: "sub:" + name }));
  for (const e of edges) {
    for (const endpoint of [e.a, e.b]) {
      if (!subNames.has(endpoint) && !graphNodes.some(n => n.id === endpoint)) {
        graphNodes.push({ id: endpoint, label: endpoint.replace(/^network:/, ""), kind: "fabric",
                          ref: endpoint });
      }
    }
  }
  const svg = document.getElementById("arch-h-svg");
  const viewport = document.getElementById("arch-h-viewport");
  const status = document.getElementById("arch-h-graph-status");
  const planes = document.getElementById("arch-h-plane");
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}) => {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, String(v)));
    return n;
  };
  const makeText = (x, y, value, size, fill, weight = 500) => {
    const t = el("text", { x, y, fill, "font-size": size, "font-weight": weight,
      "font-family": "system-ui, sans-serif", "pointer-events": "none" });
    t.textContent = value;
    return t;
  };
  const degree = new Map(graphNodes.map(n => [n.id, 0]));
  edges.filter(e => e.plane === "data").forEach(e => {
    degree.set(e.a, (degree.get(e.a) || 0) + 1);
    degree.set(e.b, (degree.get(e.b) || 0) + 1);
  });
  const order = new Map(names.map((id, i) => [id, i]));
  const dataNodes = graphNodes.filter(n => n.kind === "subsystem");
  // Arrange as connected columns by graph distance from a peripheral leaf.
  // A defined region order is an optional presentation hint, never a route.
  const regions = model.layout?.regions || [];
  const orderedByRegion = regions.flatMap(r => r.subsystems || []).filter(x => subNames.has(x));
  let levels = new Map();
  if (orderedByRegion.length === dataNodes.length && new Set(orderedByRegion).size === dataNodes.length) {
    regions.forEach((r, i) => (r.subsystems || []).forEach(name => levels.set(name, i)));
  } else {
    const active = edges.filter(e => e.plane === "data" && subNames.has(e.a) && subNames.has(e.b));
    const neighbors = new Map(names.map(n => [n, []]));
    for (const e of active) { neighbors.get(e.a).push(e.b); neighbors.get(e.b).push(e.a); }
    if (!active.length) {
      // Hub-and-spoke NoCs have no direct subsystem pairs. Avoid placing
      // every leaf into a progressively more distant column: arrange leaves
      // into a balanced grid around the separately displayed shared fabric.
      const columns = Math.ceil(Math.sqrt(Math.max(1, names.length)));
      [...names].sort().forEach((id, i) => levels.set(id, i % columns));
    } else {
      const visited = new Set();
      let offset = 0;
      for (const root of [...names].sort((a, b) =>
        (neighbors.get(a).length - neighbors.get(b).length) || a.localeCompare(b))) {
        if (visited.has(root)) continue;
        const queue = [[root, offset]];
        while (queue.length) {
          const [id, depth] = queue.shift();
          if (visited.has(id)) continue;
          visited.add(id); levels.set(id, depth);
          for (const neighbor of neighbors.get(id).sort()) if (!visited.has(neighbor)) queue.push([neighbor, depth + 1]);
        }
        offset = Math.max(...levels.values(), 0) + 2;
      }
    }
  }
  const maxLevel = Math.max(0, ...levels.values());
  const columns = new Map();
  for (const n of dataNodes) {
    const level = levels.get(n.id) || 0;
    if (!columns.has(level)) columns.set(level, []);
    columns.get(level).push(n.id);
  }
  for (const ids of columns.values()) ids.sort((a, b) => (order.get(a) - order.get(b)));
  const CARD_W = 238, CARD_H = 99, STEP_X = 295, STEP_Y = 145;
  const ncols = maxLevel + 1;
  const maxRows = Math.max(1, ...[...columns.values()].map(x => x.length));
  const W = Math.max(520, ncols * STEP_X + 85);
  const baseH = Math.max(220, maxRows * STEP_Y + 55);
  const fabrics = graphNodes.filter(n => n.kind === "fabric").sort((a, b) => a.id.localeCompare(b.id));
  const H = baseH + (fabrics.length ? fabrics.length * 97 + 50 : 0);
  const positions = new Map();
  for (const [column, ids] of columns) {
    const yOffset = Math.max(0, (maxRows - ids.length) * STEP_Y / 2);
    ids.forEach((id, i) => positions.set(id, { x: 35 + column * STEP_X, y: 35 + yOffset + i * STEP_Y }));
  }
  fabrics.forEach((n, i) =>
    positions.set(n.id, { x: Math.max(35, (W - CARD_W) / 2), y: baseH + 18 + i * 97 }));
  let selected = null, zoom = 1, panX = 0, panY = 0, dragging = null;
  let focus = {kind: "chip"}, diagramW = W, diagramH = H;
  function view() { svg.setAttribute("viewBox", [panX, panY, diagramW / zoom, diagramH / zoom].join(" ")); }
  function fit() {
    zoom = 1; panX = 0; panY = 0; view();
  }
  /*__COMPOSITION_IMPL__*/
  function draw() {
    if (focus.kind !== "chip") { drawComposition(); return; }
    diagramW = W; diagramH = H;
    svg.replaceChildren();
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    const plane = planes.value;
    const bg = el("rect", { width: W, height: H, fill: "#081522" });
    svg.append(bg);
    const count = new Map();
    for (const e of edges) {
      if (plane !== "all" && e.plane !== plane) continue;
      const a = positions.get(e.a), b = positions.get(e.b);
      if (!a || !b) continue;
      const sameColumn = Math.abs(a.x - b.x) < 5;
      let x1, y1, x2, y2;
      if (sameColumn) {
        x1 = a.x + CARD_W / 2; x2 = b.x + CARD_W / 2;
        y1 = a.y + CARD_H; y2 = b.y;
        if (y2 < y1) { y1 = a.y; y2 = b.y + CARD_H; }
      } else {
        const forward = a.x < b.x;
        x1 = a.x + (forward ? CARD_W : 0); x2 = b.x + (forward ? 0 : CARD_W);
        y1 = a.y + CARD_H / 2; y2 = b.y + CARD_H / 2;
      }
      const k = [e.a, e.b].sort().join("|") + e.plane;
      const shift = count.get(k) || 0; count.set(k, shift + 1);
      const mid = (x1 + x2) / 2 + shift * 8;
      const color = e.plane === "config" ? "#b69aff" : "#2fd1c9";
      const path = el("path", {
        d: sameColumn ? "M" + x1 + " " + y1 + " V" + y2 :
          "M" + x1 + " " + y1 + " H" + mid + " V" + y2 + " H" + x2,
        stroke: color, "stroke-width": 3, fill: "none",
        "stroke-dasharray": e.plane === "config" ? "8 6" : "none"
      });
      const hit = el("path", {
        d: path.getAttribute("d"), stroke: "transparent", "stroke-width": 17,
        fill: "none", tabindex: "0", role: "button",
        "aria-label": e.plane + " connection " + e.a + " to " + e.b
      });
      hit.addEventListener("click", () => open(e.reference));
      hit.addEventListener("keydown", ev => { if (ev.key === "Enter") open(e.reference); });
      const tt = el("title"); tt.textContent = e.name + ": " + e.a + " ⇄ " + e.b;
      hit.append(tt); svg.append(path, hit);
      // Show explicit named links at modest graph sizes; larger designs rely
      // on hover/selection so the drawing does not turn into a text wall.
      if (edges.length <= 16 && e.reference.startsWith("link:")) {
        const label = makeText(sameColumn ? x1 + 9 : mid + 7,
          sameColumn ? (y1 + y2) / 2 : Math.min(y1, y2) - 8,
          e.name.length > 30 ? e.name.slice(0, 29) + "…" : e.name,
          10, color, 650);
        svg.append(label);
      }
    }
    for (const node of graphNodes) {
      const p = positions.get(node.id);
      if (!p) continue;
      const isSelected = selected === node.id;
      const g = el("g", { tabindex: "0", role: "button", "aria-label": "Explore " + node.label });
      g.classList.add("arch-h-svg-node");
      const rect = el("rect", {
        x: p.x, y: p.y, width: CARD_W, height: CARD_H, rx: 11,
        stroke: isSelected ? "#ffffff" : node.kind === "fabric" ? "#ad8bff" : "#549bc1",
        "stroke-width": isSelected ? 3 : 1.5,
        fill: node.kind === "fabric" ? "#2b214a" : "#122f46"
      });
      const label = node.label.length > 25 ? node.label.slice(0, 24) + "…" : node.label;
      const sub = (d.subsystems || []).find(x => x.name === node.id);
      const ownNoCs = Object.entries(d.noc_profiles || {}).filter(([_, q]) =>
        q.path?.split("/")[0] === node.id).length;
      const type = d.subsystem_types?.[sub?.type] || {};
      const ipName = sub?.cpu?.ip || sub?.ip || type.dma || sub?.type || "Subsystem";
      const mapped = (model.address_map?.data || []).filter(a => a.name?.startsWith(node.id + "."));
      const memories = (d.memory_targets || []).filter(m => m.name.startsWith(node.id + "."));
      const mappedText = memories.length ? memories.map(m => m.kind.toUpperCase()).join(" / ") :
        mapped.some(a => a.name.endsWith(".sram")) ? "SRAM" : "Mapped endpoints";
      g.append(rect, makeText(p.x + 13, p.y + 26, label, 15, "#eaf4ff", 700),
               makeText(p.x + 13, p.y + 50,
                 node.kind === "fabric" ? "Shared network" : ipName, 12, "#a4bfd0"),
               makeText(p.x + 13, p.y + 76,
                 node.kind === "fabric" ? "Click for router / NI view" :
                 mappedText + " • " + ownNoCs + " local NoCs • open ›",
                 11, "#7bd5da"));
      const tt = el("title"); tt.textContent = node.label + " — click to inspect";
      g.append(tt);
      g.addEventListener("click", () => { selected = node.id; draw(); open(node.ref); });
      g.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selected = node.id; draw(); open(node.ref); }
      });
      svg.append(g);
    }
    status.textContent = graphNodes.length + " blocks · " + edges.filter(e => plane === "all" || e.plane === plane).length +
      " connections · configuration-derived, not runtime-verified";
  }
  function open(ref) {
    if (typeof window.archHierarchyNavigate === "function") {
      window.archHierarchyNavigate(ref);
    } else {
      showFocus(ref);
    }
  }
  function showFocus(id) {
    if (id === "chip" || id === "subsystems") focus = {kind: "chip"};
    else if (id.startsWith("sub:")) focus = {kind:"subsystem", id:id.slice(4)};
    else if (id.startsWith("noc:")) focus = {kind:"noc", id:id.slice(4)};
    else if ((id.startsWith("network:") || id.startsWith("fabric:")) &&
             d.noc_profiles?.[id.split(":")[1]])
      focus = {kind:"noc", id:id.split(":")[1]};
    else if (id.startsWith("router:")) {
      const parts=id.slice(7).split(":");
      if(parts.length===3 && Number.isInteger(+parts[1]) && Number.isInteger(+parts[2]))
        focus={kind:"router",noc:parts[0],x:+parts[1],y:+parts[2]};
    } else if (id.startsWith("endpoint:")) {
      const bits=id.slice(9).split(":");
      if(bits.length===2) focus={kind:"endpoint",noc:bits[0],endpoint:bits[1]};
    } else if (id.startsWith("ip:") || id.startsWith("profile:") || id.startsWith("property:")) {
      const bits=id.split(":");
      if (bits.length===3 && subNames.has(bits[1]))
        focus={kind:"ip",sub:bits[1],id:bits[2]};
    } else if (id.startsWith("memory:") || id.startsWith("region:")) {
      const sub=id.split(":")[1].split(".")[0];
      if (subNames.has(sub)) focus={kind:"subsystem",id:sub};
    }
    draw(); updateVisualBread();
  }
  function updateVisualBread() {
    const crumb=document.getElementById("arch-h-diagram-crumbs");
    if(!crumb)return;
    const spans=[{label:"Chip",id:"chip"}];
    if(focus.kind==="subsystem")spans.push({label:focus.id,id:"sub:"+focus.id});
    if(focus.kind==="noc")spans.push({label:focus.id,id:"noc:"+focus.id});
    if(focus.kind==="ip")spans.push({label:focus.sub,id:"sub:"+focus.sub},
      {label:focus.id,id:"ip:"+focus.sub+":"+focus.id});
    if(focus.kind==="router"||focus.kind==="endpoint"){
      spans.push({label:focus.noc,id:"noc:"+focus.noc});
      spans.push({label:focus.kind==="router"?
        "["+focus.x+","+focus.y+"]":focus.endpoint,
        id:focus.kind==="router"?"router:"+focus.noc+":"+focus.x+":"+focus.y:
          "endpoint:"+focus.noc+":"+focus.endpoint});
    }
    crumb.replaceChildren();
    for (const [idx,item] of spans.entries()) {
      if(idx) {const sep=document.createElement("span");sep.textContent=" / ";crumb.append(sep);}
      const b=document.createElement("button");b.type="button";b.textContent=item.label;
      b.addEventListener("click",()=>open(item.id));crumb.append(b);
    }
  }
  const zoomTo = k => { zoom = Math.max(0.45, Math.min(3, zoom * k)); view(); };
  document.getElementById("arch-h-zoom-in").addEventListener("click", () => zoomTo(1.25));
  document.getElementById("arch-h-zoom-out").addEventListener("click", () => zoomTo(1 / 1.25));
  document.getElementById("arch-h-fit").addEventListener("click", fit);
  planes.addEventListener("change", draw);
  viewport.addEventListener("wheel", ev => {
    if (!ev.ctrlKey) return;
    ev.preventDefault();
    zoomTo(ev.deltaY < 0 ? 1.1 : 0.9);
  }, { passive: false });
  svg.addEventListener("pointerdown", ev => {
    if (ev.target.closest(".arch-h-svg-node")) return;
    dragging = { x: ev.clientX, y: ev.clientY, panX, panY };
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", ev => {
    if (!dragging) return;
    const rect = svg.getBoundingClientRect();
    panX = dragging.panX - (ev.clientX - dragging.x) * (W / zoom / rect.width);
    panY = dragging.panY - (ev.clientY - dragging.y) * (H / zoom / rect.height);
    view();
  });
  svg.addEventListener("pointerup", () => { dragging = null; });
  svg.addEventListener("pointercancel", () => { dragging = null; });
  window.addEventListener("arch-h-selected", ev => {
    const id = ev.detail?.id;
    const n = graphNodes.find(node => node.ref === id);
    if (n) selected = n.id;
    if(id)showFocus(id);
  });
  fit(); draw(); updateVisualBread();
})();
