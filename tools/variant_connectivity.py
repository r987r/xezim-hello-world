#!/usr/bin/env python3
"""Exact-selected-chip variant connectivity; never equate declarations with traffic.

Reads the *generated variant RTL*, chip/FlooGen manifests, the selected AXI
monitor catalog and actor map from one regression attempt. A live attachment
is a generator-owned structural claim until the selected RTL compiles; it is
never called elaborated or observed by this pre-run tool. The canonical
default topology remains unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

import yaml

from interface_contracts import build as interface_contracts
from fabric_report import contract_port, owner
from noc_diagrams import diagram_gen_metadata, read_generated_nocs


class VariantEvidenceError(ValueError):
    pass


def required_json(root: Path, relative: str) -> tuple[Path, dict]:
    if not isinstance(relative, str) or not relative:
        raise VariantEvidenceError("missing required source path")
    path=(root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.is_symlink():
        raise VariantEvidenceError("missing/unsafe variant source " + relative)
    data=json.loads(path.read_text())
    if not isinstance(data,dict):
        raise VariantEvidenceError("invalid source JSON " + relative)
    return path,data


def digest(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise VariantEvidenceError("missing/unsafe source for digest: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(root: Path, path: Path) -> str:
    path=path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise VariantEvidenceError("source escapes repository: " + str(path))
    return path.relative_to(root.resolve()).as_posix()


def declared_edge(graph: dict, src: str, dst: str) -> dict:
    found=[link for link in graph["connections"]
           if link["from"]["instance"]==src and link["to"]["instance"]==dst]
    if len(found)!=1:
        raise VariantEvidenceError(f"missing/ambiguous source graph edge {src} -> {dst}")
    return found[0]


def reconcile(graph: dict, cfg: dict, chip: dict, actors: dict, monitors: list) -> dict:
    """Promote only selected generator-declared attachments, never PHY/traffic."""
    ports={m["id"]:m for m in monitors}
    if len(ports)!=len(monitors):
        raise VariantEvidenceError("duplicate passive monitor IDs")
    peripheral={r["name"]:r for r in chip.get("peripheral_subsystems",[])}
    names={s["name"]:s for s in cfg["subsystems"] if s["type"]=="peripheral"}
    if set(peripheral)!=set(names):
        raise VariantEvidenceError("generated chip peripheral inventory differs from selected SoC")
    states={}
    for name,sub in sorted(names.items()):
        src=peripheral[name]
        if src.get("ip")!=sub["ip"]:
            raise VariantEvidenceError("peripheral generator IP differs from SoC")
        if (src.get("local_data_noc")!=name+"_local_data"
                or src.get("local_config_noc")!=name+"_local_config"):
            raise VariantEvidenceError("peripheral NoC ports differ from generator")
        actor_id=name+"_local_data."+sub["data_initiator"]
        packet=declared_edge(graph,name+".ip",actor_id)
        mgmt=declared_edge(graph,name+".ip",
                           name+"_local_config."+sub["config_initiator"])
        regs=declared_edge(graph,name+"_local_config.controller_regs",name+".csr")
        attachment=src["rtl_attachment"]
        live=attachment.startswith("live_")
        if not live and attachment!="reserved_idle":
            raise VariantEvidenceError("unknown peripheral source attachment: "+attachment)
        if live:
            if actor_id not in ports or ports[actor_id].get("role")!="initiator":
                raise VariantEvidenceError("live peripheral has no source-bound AXI monitor: "+actor_id)
            if not str(actors.get(actor_id,{}).get("kind","")).startswith("rtl_"):
                raise VariantEvidenceError("live peripheral has no RTL actor declaration: "+actor_id)
            packet["status"]="generated_variant_declared_live_not_elaborated"
            packet["type"]="axi_interconnect"
            packet["name"]="Selected generated "+name+" RTL to local data NoC"
        else:
            if str(actors.get(actor_id,{}).get("kind","")).startswith("rtl_"):
                raise VariantEvidenceError("reserved peripheral has an active RTL actor: "+actor_id)
            packet["status"]="planned_integration"
        # A device does not automatically initiate its own configuration NoC.
        # A live Ethernet *target* CSR is represented by controller_regs, not
        # by incorrectly turning the device management source edge on.
        mgmt["status"]="planned_integration"
        csr=src["csr_attachment"]
        if csr.startswith("live_"):
            target=name+"_local_config.controller_regs"
            if target not in ports or ports[target].get("role")!="target":
                raise VariantEvidenceError("live peripheral CSR missing AXI target monitor")
            if not str(actors.get(target,{}).get("kind","")).startswith("rtl_"):
                raise VariantEvidenceError("live peripheral CSR missing RTL actor")
            regs["status"]="generated_variant_declared_live_not_elaborated"
            regs["name"]="Selected generated "+name+" queue/control registers"
        elif csr!="explicit_axi_error":
            raise VariantEvidenceError("unexpected peripheral CSR attachment: "+csr)
        states[name]={
            "ip":src["ip"],"data_noc":src["local_data_noc"],
            "config_noc":src["local_config_noc"],
            "data_actor":actor_id,"data_attachment":attachment,
            "config_attachment":csr,
            "data_status":"generated_source_declared_live_not_elaborated" if live else "reserved_no_packet_engine",
            "csr_status":"generated_source_declared_live_not_elaborated" if csr.startswith("live_") else "error_responder",
        }
    if chip.get("real_ddr_controller"):
        c=declared_edge(graph,"memory0_local_config.controller_regs","memory0.ctrl")
        c["status"]="generated_variant_declared_live_not_elaborated"
        c["name"]="Generated pinned LiteDRAM Config NoC target"
        d=declared_edge(graph,"memory0.internal_target_crossbar","memory0.ddr0")
        d["status"]="generated_variant_declared_live_not_elaborated"
        d["name"]="Generated pinned LiteDRAM controller (behavioral DFI)"
    graph["scope_note"]=(
        "Exactly selected generated chip variant; active links are GENERATOR DECLARATIONS, "
        "not elaborated port/bit proof or observed traffic. Config and data NoCs "
        "are structural; DDR DFI uses a behavioral PHY. Refer to the original "
        "passive protocol report to establish run-time activity.")
    graph["status"]="selected_generated_variant_topology_not_elaborated"
    return states


def collect(root: Path, target: str, plan: dict, out: Path) -> tuple[dict,dict]:
    root=root.resolve();out=out.resolve()
    axi=(plan.get("report") or {}).get("axi")
    if not axi or plan.get("top") not in ("full_chip_tb","full_chip_dma_tb"):
        raise VariantEvidenceError("only source-qualified full-chip AXI target supported")
    selected=(out/"variant/manifest.json")
    variant=selected.is_file()
    if plan.get("firmware_mode") in (
            "cpu_dma","cpu_dma_scenario","ethernet_mvp","ethernet_cpu",
            "pcie_host","pcie_dma_host","ddr_cpu_dma") and not variant:
        raise VariantEvidenceError("expected generated selected RTL variant is missing")
    chip_path=selected if variant else root/"gen/chip/manifest.json"
    chip=json.loads(chip_path.read_text())
    top=(out/"variant/soc_top.sv" if variant else root/"gen/chip/soc_top.sv")
    tb=(out/"variant"/(plan["top"]+".sv") if variant else root/"gen/chip"/(plan["top"]+".sv"))
    real_ddr=(out/"ddr_noc/soc.yaml").is_file()
    if chip.get("real_ddr_controller",False)!=real_ddr:
        raise VariantEvidenceError("DDR controller flag and source-generated NoC disagree")
    noc_root=(out/"ddr_noc/noc/floonoc" if real_ddr else root/"gen/noc/floonoc")
    super_root=(out/"ddr_noc/supernoc" if real_ddr else root/"gen/supernoc")
    noc_soc=(out/"ddr_noc/soc.yaml" if real_ddr else root/"config/soc.yaml")
    if real_ddr and not variant:
        raise VariantEvidenceError("DDR variant unexpectedly uses checked-in RTL")
    selected_sources={str(Path(s).resolve()) for s in plan.get("sources",[])}
    for source in (top,tb,super_root/"soc_noc.sv"):
        if str(source.resolve()) not in selected_sources:
            raise VariantEvidenceError("selected RTL file not in exact run filelist: "+str(source))
    _,catalog=required_json(root,axi["catalog"])
    _,actor_doc=required_json(root,axi["actors"])
    monitors=catalog.get("monitors")
    actors=actor_doc.get("axi_actors")
    if catalog.get("schema_version")!=1 or not isinstance(monitors,list) or not isinstance(actors,dict):
        raise VariantEvidenceError("selected monitor/actor catalog invalid")
    networks=read_generated_nocs(noc_root)
    cfg=yaml.safe_load(noc_soc.read_text())
    knobs=yaml.safe_load((root/"config/interface_contracts.yaml").read_text())
    knobs_ports=interface_contracts(cfg,knobs,networks["global_data"]["config"])["ports"]
    super_manifest=json.loads((super_root/"manifest.json").read_text())
    if set(networks)!=set(json.loads((noc_root/"manifest.json").read_text())["networks"]):
        raise VariantEvidenceError("NoC network source set drift")
    graph=diagram_gen_metadata(cfg,networks)
    graph["source_of_truth"]=[
        rel(root,noc_soc),rel(root,noc_root/"manifest.json"),
        rel(root,chip_path),rel(root,top),rel(root,super_root/"soc_noc.sv"),
        rel(root,root/"config/interface_contracts.yaml")]
    states=reconcile(graph,cfg,chip,actors,monitors)
    # Check the *selected* generated source actually contains each
    # generator-named module/instance token. This is stronger than merely
    # reading an actor manifest, but still NOT compiler/elaboration proof.
    top_text=top.read_text()
    for name,state in states.items():
        record=next(p for p in chip["peripheral_subsystems"] if p["name"]==name)
        def require_instance(module_key,instance_key):
            mod=record.get(module_key)
            inst=record.get(instance_key)
            if (not isinstance(mod,str) or not isinstance(inst,str)
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",mod)
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",inst)
                    or not re.search(r"\\b"+re.escape(mod)+r"\\s*#",top_text)
                    or not re.search(r"\\b"+re.escape(inst)+r"\\s*\\(",top_text)):
                raise VariantEvidenceError("selected RTL missing generator-named "
                                           "instance for "+name+" "+module_key)
        if state["data_status"].startswith("generated_"):
            require_instance("rtl_module","rtl_instance")
            state["rtl_module"]=record["rtl_module"]
            state["rtl_instance"]=record["rtl_instance"]
            state["source_instance_evidence"]="generator_named_source_tokens_not_elaborated"
        if state["csr_status"].startswith("generated_"):
            require_instance("csr_module","csr_instance")
            state["csr_module"]=record["csr_module"]
            state["csr_instance"]=record["csr_instance"]

    # Audit the very signals that the real Cocotb AXI monitor binds in the
    # selected soc_noc RTL (not just the generator's manifest list).
    rtl_taps=(super_root/"soc_noc.sv").read_text()
    known=set()
    boundaries=[]
    subsystem_names={s["name"] for s in cfg["subsystems"]}
    for monitor in monitors:
        mid=monitor.get("id")
        if not isinstance(mid,str) or mid in known:
            raise VariantEvidenceError("missing or duplicate AXI monitor identity")
        known.add(mid)
        network=monitor.get("network")
        endpoint=mid.partition(".")[2]
        if network not in networks or endpoint not in networks[network]["endpoints"]:
            raise VariantEvidenceError("selected monitor is not a generated NoC endpoint: "+mid)
        proto=networks[network]["config"]["protocols"]
        item=networks[network]["endpoints"][endpoint]
        pname=(item.get("mgr_port_protocol") or item.get("sbr_port_protocol"))[0]
        model=next((p for p in proto if p["name"]==pname),None)
        if (model is None or
                (monitor["role"]=="initiator") != bool(item.get("mgr_port_protocol")) or
                any(monitor.get(a)!=model[b] for a,b in (
                    ("addr_width","addr_width"),("data_width","data_width"),("id_width","id_width")))):
            raise VariantEvidenceError("AXI monitor widths or role differ from pinned FlooGen: "+mid)
        prefix=monitor.get("prefix")
        if not isinstance(prefix,str) or not all(
                prefix+"_"+channel in rtl_taps for channel in ("awvalid","arvalid","bvalid","rvalid")):
            raise VariantEvidenceError("selected AXI monitor taps not in generated soc_noc RTL: "+mid)
        sub=owner(network,subsystem_names)
        port=contract_port(network,endpoint,sub)
        budget=knobs_ports.get(port) if port else None
        budget_origin=port if budget else "plane_default"
        if budget is None:
            budget=knobs["defaults"]["axi4" if monitor["plane"]=="data" else "axi4_lite"]
        actor=actors.get(mid,{"kind":"interconnect","label":"Inter-NoC boundary (no endpoint actor)"})
        if not isinstance(actor,dict) or not isinstance(actor.get("kind"),str):
            raise VariantEvidenceError("invalid selected AXI actor: "+mid)
        boundaries.append({
            "id":mid,"network":network,"subsystem":sub,
            "plane":monitor["plane"],"role":monitor["role"],
            "interface_name":endpoint+"_axi_"+("in" if monitor["role"]=="initiator" else "out"),
            "address_bits":model["addr_width"],"data_bits":model["data_width"],
            "axi_id_bits":model["id_width"],
            "max_pending_reads_budget":budget["max_pending_reads"],
            "max_pending_writes_budget":budget["max_pending_writes"],
            "configured_budget_source":budget_origin,
            "fabric_shared_MaxTxns":networks[network]["entry"]["native_parameters"]["MaxTxns"],
            "clock":"clk_i","clock_domain":"soc_single_clock",
            "actor_kind":actor["kind"],"actor_label":actor.get("label",mid),
            "monitor_prefix":prefix,
            "monitor_provenance":"taps_in_selected_generated_soc_noc_not_simulation",
            "observed_requests":None,
            "runtime_status":"not_measured_before_execution",
        })
    missing=set(actors)-known
    # Generator may name unexposed inter-NoC actors, but a claimed live RTL
    # initiator/target MUST be instrumented by the selected passive catalog.
    bad=[k for k in missing if str(actors[k].get("kind","")).startswith("rtl_")]
    if bad:
        raise VariantEvidenceError("claimed live RTL actors have no AXI monitor: "+str(sorted(bad)))
    if len(boundaries)!=len(monitors) or not boundaries:
        raise VariantEvidenceError("incomplete selected AXI monitor inventory")
    expected={str((out/"variant/soc_top.sv" if variant else root/"gen/chip/soc_top.sv").resolve()),
              str((super_root/"soc_noc.sv").resolve())}
    if not expected.issubset(selected_sources):
        raise VariantEvidenceError("selected chip/fabric RTL source closure incomplete")
    sources=[top,tb,super_root/"soc_noc.sv",chip_path,
             noc_soc,noc_root/"manifest.json",super_root/"manifest.json",
             root/"config/interface_contracts.yaml"]
    sources.extend([root/axi["catalog"],root/axi["actors"]])
    digests={rel(root,f):digest(f) for f in sources}
    graph["variant_source_manifest_sha256"]=digests[rel(root,chip_path)]
    graph["variant_top_source_sha256"]=digests[rel(root,top)]
    result={
        "schema_version":1,"target":target,"firmware_mode":plan.get("firmware_mode"),
        "top":plan["top"],"chip_variant":"generated_per_test" if variant else "checked_in_default",
        "source_proof":"generator_manifest_plus_selected_RTL_filelist_plus_actual_AXImon_taps_not_elaboration",
        "elaborated":False,"observed_protocol_traffic":False,
        "source_sha256":digests,
        "source_manifest":rel(root,chip_path),
        "selected_soc_top":rel(root,top),
        "topology":"variant-topology.json",
        "networks":[{"name":name,"plane":n["entry"]["plane"],"routers":n["entry"]["routers"],
                     "native_MaxTxns_shared":n["entry"]["native_parameters"]["MaxTxns"]}
                    for name,n in sorted(networks.items())],
        "peripherals":states,
        "boundaries":boundaries,
        "summary":{
            "meshes":len(networks),
            "routers":sum(n["entry"]["routers"] for n in networks.values()),
            "monitors":len(boundaries),
            "initiators":sum(b["role"]=="initiator" for b in boundaries),
            "targets":sum(b["role"]=="target" for b in boundaries),
            "declared_live_peripherals":sum(x["data_status"].startswith("generated_") for x in states.values()),
        },
    }
    return result,graph


def publish(root: Path, target: str, plan: dict, out: Path) -> dict:
    result,graph=collect(root,target,plan,out)
    for filename,data in (("variant-connectivity.json",result),("variant-topology.json",graph)):
        (out/filename).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    return result
