#!/usr/bin/env python3
"""Publish a read-only, address-accurate SoC fabric inventory and route matrix.

This *does not* estimate router latency or claim reserved DMA/controllers work.
FlooGen profiles and the shared super-NoC manifest are the routing authority;
interface_contracts supplies planned budgets, never independently proven RTL caps.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from math import ceil
from statistics import mean, median
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class FabricReportError(ValueError):
    pass


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def windows(endpoint):
    regions = endpoint.get("addr_range") or []
    return [regions] if isinstance(regions, dict) else regions


def owner(network, subsystem_names):
    for name in sorted(subsystem_names, key=len, reverse=True):
        if network.startswith(name + "_"):
            return name
    if network.startswith("global_"):
        return "global"
    raise FabricReportError(f"unknown owning subsystem for {network}")


def contract_port(network, endpoint, subsystem):
    """Expose known planned port contracts while preserving unknown as None."""
    if network == "global_data":
        if endpoint.endswith("_sram") or endpoint.startswith("memory_ingress"):
            return None
        return "global_data." + endpoint + "_in"
    if network == "global_config":
        if endpoint.endswith("_regs"):
            return "global_config." + endpoint[:-5] + "_out"
        return "global_config." + endpoint + "_in"
    if network == subsystem + "_local_data":
        return {"cpu":f"{subsystem}.local_data.cpu_in",
                "dma":f"{subsystem}.local_data.dma_in",
                "host":f"{subsystem}.local_data.data_in",
                "global_in":f"{subsystem}.local_data.global_in",
                "sram":f"{subsystem}.local_data.sram_out",
                "global_out":f"{subsystem}.local_data.global_out"}.get(endpoint)
    if network == subsystem + "_local_config":
        return {"cpu":f"{subsystem}.local_config.cpu_in",
                "management":f"{subsystem}.local_config.config_in",
                "global_in":f"{subsystem}.local_config.global_in",
                "dma_regs":f"{subsystem}.local_config.dma_csr_out",
                "controller_regs":f"{subsystem}.local_config.controller_regs_out",
                "reset_ctrl":f"{subsystem}.local_config.reset_ctrl_out",
                "global_out":f"{subsystem}.local_config.global_out"}.get(endpoint)
    return None


def xy_routers(start, stop, network):
    x, y = start
    xx, yy = stop
    nodes = [f"{network}.router_{x}_{y}"]
    while x != xx:
        x += 1 if xx > x else -1
        nodes.append(f"{network}.router_{x}_{y}")
    while y != yy:
        y += 1 if yy > y else -1
        nodes.append(f"{network}.router_{x}_{y}")
    return nodes


def prepare_networks(manifest, root):
    networks = {}
    for name, entry in sorted(manifest["networks"].items()):
        profile = yaml.safe_load((root / entry["config"]).read_text())
        if profile["routing"]["route_algo"] != "XY":
            raise FabricReportError(f"{name}: only upstream-generated XY routing is characterized")
        dims = profile["routers"][0]["array"]
        if dims[0] * dims[1] != entry["routers"]:
            raise FabricReportError(f"{name}: router count mismatch")
        ports = {e["name"]: e for e in profile["endpoints"]}
        if len(ports) != entry["endpoint_count"]:
            raise FabricReportError(f"{name}: endpoint count mismatch")
        positions = {}
        for link in profile["connections"]:
            if link["src"] not in ports or link["src"] in positions or link["dst"] != "router":
                raise FabricReportError(f"{name}: bad or duplicated NI attachment")
            coords = tuple(link["dst_idx"])
            if len(coords) != 2 or not (0 <= coords[0] < dims[0] and 0 <= coords[1] < dims[1]):
                raise FabricReportError(f"{name}: out-of-range NI attachment")
            positions[link["src"]] = coords
        if positions.keys() != ports.keys():
            raise FabricReportError(f"{name}: missing NI attachment")
        protocols = {p["name"]: p for p in profile["protocols"]}
        networks[name] = {"entry": entry, "profile": profile, "ports": ports,
                          "positions": positions, "protocols": protocols}
    return networks


def trace(start, address, networks, links):
    """Follow upstream FlooGen decoder + shared cross-network wiring."""
    current, seen, stages, names = start, set(), [], []
    while current not in seen:
        seen.add(current)
        network, ingress = current.split(".", 1)
        if network not in networks or ingress not in networks[network]["ports"]:
            raise FabricReportError(f"invalid route endpoint {current}")
        n = networks[network]
        matches = [name for name, ep in n["ports"].items()
                   if ep.get("sbr_port_protocol") and any(
                       number(r["base"]) <= address < number(r["base"]) + number(r["size"])
                       for r in windows(ep))]
        if len(matches) != 1:
            raise FabricReportError(f"{current}: ambiguous/missing decoder for 0x{address:x}: {matches}")
        egress = matches[0]
        path = xy_routers(n["positions"][ingress], n["positions"][egress], network)
        stages.append({"kind": "mesh", "network": network, "from": current,
                       "to": f"{network}.{egress}", "routers": path,
                       "router_links": len(path) - 1, "latency_cycles": None})
        names.append(network)
        out = f"{network}.{egress}"
        if out not in links:
            return out, stages, names
        dst = links[out]
        stages.append({"kind": "inter_mesh_axi", "from": out, "to": dst,
                       "router_links": 0, "latency_cycles": None})
        current = dst
    raise FabricReportError(f"cyclic NoC route from {start} @ 0x{address:x}")


def build(soc, knobs, noc_manifest, networks, super_manifest, chip_manifest, ports):
    address_map = {plane: {e["name"]: e for e in soc["address_map"][plane]}
                   for plane in ("data", "config")}
    targets = []
    for plane, entries in address_map.items():
        for name, r in sorted(entries.items()):
            targets.append({"name": name, "plane": plane, "address_base": f"0x{number(r['base']):x}",
                            "address_size": f"0x{number(r['size']):x}",
                            "target_read_latency_cycles": None,
                            "target_write_latency_cycles": None,
                            "latency_status": "unmeasured"})
    target_by_name = {t["name"]: t for t in targets}
    contract_ports = ports
    actors = chip_manifest["axi_actors"]
    names = {s["name"] for s in soc["subsystems"]}
    inventory = []
    for netname, n in sorted(networks.items()):
        sub = owner(netname, names)
        plane = n["entry"]["plane"]
        for epname, ep in sorted(n["ports"].items()):
            role = "initiator" if ep.get("mgr_port_protocol") else "target"
            protocols = ep.get("mgr_port_protocol") or ep.get("sbr_port_protocol")
            if len(protocols) != 1 or protocols[0] not in n["protocols"]:
                raise FabricReportError(f"{netname}.{epname}: invalid protocol")
            protocol = n["protocols"][protocols[0]]
            cname = contract_port(netname, epname, sub)
            budget = contract_ports.get(cname) if cname else None
            if budget is None:
                budget = knobs["defaults"]["axi4" if plane == "data" else "axi4_lite"]
            identity = f"{netname}.{epname}"
            actor = actors.get(identity, {"kind": "interconnect", "label": "Inter-NoC fabric boundary"})
            inventory.append({"name": identity, "subsystem": sub, "fabric": netname,
                              "interface_name": f"{epname}_axi_{'in' if role == 'initiator' else 'out'}",
                              "role": role, "plane": plane, "protocol": "axi4_transport",
                              "endpoint_protocol": "axi4_lite" if plane == "config" else "axi4",
                              "data_bits": protocol["data_width"], "addr_bits": protocol["addr_width"],
                              "id_bits": protocol["id_width"], "max_burst_beats": budget["max_burst_beats"],
                              "max_pending_reads_budget": budget["max_pending_reads"],
                              "max_pending_writes_budget": budget["max_pending_writes"],
                              "budget_source": cname if cname in contract_ports else "plane_default",
                              "fabric_shared_max_txns": n["entry"]["native_parameters"]["MaxTxns"],
                              "fabric_max_unique_ids": n["entry"]["native_parameters"]["MaxUniqueIds"],
                              "clock_signal": "clk_i", "clock_domain": "soc_single_clock",
                              "clock_frequency_hz": None,
                              "integration": actor["kind"], "actor": actor["label"],
                              "router": f"{netname}.router_{n['positions'][epname][0]}_{n['positions'][epname][1]}",
                              "address_windows": [{"base": f"0x{number(x['base']):x}",
                                                   "size": f"0x{number(x['size']):x}"} for x in windows(ep)]})
    # Physical controller ports are not integrated; the logical AXI models behind
    # the existing target crossbar still need explicit inventory rows.
    for memory in soc["memory_targets"]:
        target = memory["name"]
        sub = target.split(".")[0]
        port_name = f"{sub}.memory_data.{target.split('.')[-1]}_out"
        contract = contract_ports.get(port_name)
        if contract is None:
            raise FabricReportError(f"missing target interface contract: {port_name}")
        inventory.append({"name": target, "subsystem": sub,
                          "fabric": f"{sub}.memory_data", "interface_name": port_name,
                          "role": "target", "plane": "data", "protocol": "axi4_model",
                          "endpoint_protocol": "axi4", "data_bits": contract["data_bits"],
                          "addr_bits": contract["addr_bits"], "id_bits": contract["id_bits"],
                          "max_burst_beats": contract["max_burst_beats"],
                          "max_pending_reads_budget": contract["max_pending_reads"],
                          "max_pending_writes_budget": contract["max_pending_writes"],
                          "budget_source": port_name, "fabric_shared_max_txns": None,
                          "fabric_max_unique_ids": None, "clock_signal": "clk_i",
                          "clock_domain": "soc_single_clock", "clock_frequency_hz": None,
                          "integration": "behavioral_memory_model",
                          "actor": "AXI-backed SRAM model, not a DDR/HBM controller",
                          "router": None,
                          "address_windows": [{"base": target_by_name[target]["address_base"],
                                               "size": target_by_name[target]["address_size"]}]})
    by_interface = {p["name"]: p for p in inventory}
    links = {}
    linked_inputs = set()
    for line in super_manifest["connections"]:
        a, b = line["from"], line["to"]
        if a in links or b in linked_inputs or a not in by_interface or b not in by_interface:
            raise FabricReportError(f"duplicate/unknown inter-mesh link {a} -> {b}")
        if by_interface[a]["role"] != "target" or by_interface[b]["role"] != "initiator":
            raise FabricReportError(f"invalid inter-mesh direction {a} -> {b}")
        if any(by_interface[a][attr] != by_interface[b][attr]
               for attr in ("plane", "addr_bits", "data_bits", "id_bits")):
            raise FabricReportError(f"incompatible inter-mesh AXI widths {a} -> {b}")
        links[a] = b
        linked_inputs.add(b)
    masters = [f"{m['network']}.{m['endpoint']}" for m in super_manifest["masters"]]
    if len(masters) != len(set(masters)):
        raise FabricReportError("duplicate external initiator")
    routes, matrix = [], []
    for m in super_manifest["masters"]:
        source = f"{m['network']}.{m['endpoint']}"
        if source not in by_interface or by_interface[source]["role"] != "initiator":
            raise FabricReportError(f"missing external initiator: {source}")
        plane = m["plane"]
        for target in (t for t in targets if t["plane"] == plane):
            label, base, size = target["name"], number(target["address_base"]), number(target["address_size"])
            candidates = [r for r in m["regions"] if number(r["base"]) <= base and
                          base + size <= number(r["base"]) + number(r["size"])]
            if not candidates:
                matrix.append({"source": source, "target": label, "plane": plane,
                               "access": "none", "route_id": None})
                continue
            if len(candidates) != 1:
                raise FabricReportError(f"multiple matching windows: {source} -> {label}")
            permission = candidates[0]["access"]
            if permission not in ("read", "read_write"):
                raise FabricReportError(f"unknown access policy {permission}")
            final, stages, visited = trace(source, base, networks, links)
            expected = candidates[0]["destination"]
            actual = "s_" + final.replace(".", "_", 1)
            if actual != expected or visited != candidates[0]["networks"]:
                raise FabricReportError(f"route/manifest divergence {source} -> {label}: "
                                        f"{actual}/{visited} != {expected}/{candidates[0]['networks']}")
            if label.startswith("memory0.") and label in {x["name"] for x in soc["memory_targets"]}:
                if not final.endswith(".target_crossbar"):
                    raise FabricReportError(f"{label}: missing memory crossbar")
                stages.append({"kind": "memory_crossbar", "from": final, "to": label,
                               "router_links": 0, "latency_cycles": None})
            else:
                real_name = ("boot." + final.split(".")[-1][5:] if final.endswith((".boot_rom", ".boot_flash"))
                             else final.split("_local_")[0] + "." + final.split(".")[-1])
                aliases = {"boot_rom": "boot.rom", "boot_flash": "boot.flash",
                           "controller_regs": final.split("_local_")[0] + ".ctrl", "dma_regs": label,
                           "reset_ctrl": "boot.reset_ctrl"}
                real_name = aliases.get(final.split(".")[-1], real_name)
                if real_name != label:
                    raise FabricReportError(f"route terminates at {real_name} not {label}")
            stages.append({"kind": "target_service", "from": label, "to": label,
                           "router_links": 0, "latency_cycles": None})
            if trace(source, base + size - 1, networks, links)[0] != final:
                raise FabricReportError(f"window changes endpoint: {source} -> {label}")
            route_id = f"{source}->{label}"
            hops = sum(s["router_links"] for s in stages)
            route = {"id": route_id, "source": source, "target": label, "plane": plane,
                     "access": "R" if permission == "read" else "RW",
                     "source_integration": by_interface[source]["integration"],
                     "target_integration": ("behavioral_memory_model" if label in {x["name"] for x in soc["memory_targets"]}
                                            else by_interface[final]["integration"]),
                     "network_count": len(visited), "router_links": hops,
                     "inter_mesh_links": len(visited) - 1,
                     "network_path": visited, "stages": stages,
                     "latency": {"transaction": "one_beat", "request_cycles": None,
                                 "target_read_cycles": None, "target_write_cycles": None,
                                 "response_cycles": None, "end_to_end_read_cycles": None,
                                 "end_to_end_write_cycles": None, "status": "unmeasured"}}
            route["one_beat_observations"] = []
            routes.append(route)
            matrix.append({"source": source, "target": label, "plane": plane,
                           "access": route["access"], "route_id": route_id,
                           "router_links": hops, "inter_mesh_links": len(visited) - 1,
                           "target_read_latency_cycles": None,
                           "target_write_latency_cycles": None})
    return {"schema_version": 1,
            "source_of_truth": ["config/soc.yaml", "config/interface_contracts.yaml",
                                "gen/noc/floonoc/manifest.json", "gen/noc/floonoc/**/floogen.yaml",
                                "gen/supernoc/manifest.json", "gen/chip/manifest.json"],
            "scope": "chip_boot_configuration_topology",
            "timing_note": "Router counts are structural. Per-mesh AXI timings require clean "
                           "source-SHA-matched serial baseline evidence. Hardware clock frequency, "
                           "individual router cycles and physical device latency remain unknown.",
            "summary": {"interfaces": len(inventory), "initiators": len(masters),
                        "targets": len(targets), "reachable_routes": len(routes),
                        "meshes": len(networks), "cross_mesh_links": len(links)},
            "interfaces": inventory, "targets": targets, "initiators": masters,
            "matrix": matrix, "routes": routes}




def _observed_transfers(rows, phase):
    """Index only unambiguous, accepted, successful single-beat transfers."""
    observed = defaultdict(list)
    for tx in rows:
        if (tx.get("phase") != phase or tx.get("status") != "complete"
                or tx.get("expected_beats") != 1 or tx.get("issues")
                or number(tx.get("response") or 0) != 0
                or tx.get("start_ps") is None or tx.get("end_ps") is None
                or tx["end_ps"] < tx["start_ps"]):
            continue
        observed[(tx["monitor"], tx["plane"], tx["operation"],
                  number(tx["address"]))].append(tx)
    return observed


def _observed_stages(route, source_tx, transfer_index, boundary):
    """Pair a serial transaction across tapped AXI boundaries.

    The baseline has at most one outstanding transaction *across the design*
    and uses unique addresses. Consequently a matching address/operation at
    a *known on-route* AXI boundary is unambiguous without depending on AXI
    ID remapping. Reject any missing, duplicate or nonmonotonic observation.
    Router-internal flits and post-crossbar target AXI ports are NOT tapped.
    """
    key = (route["plane"], source_tx["operation"], number(source_tx["address"]))
    stages = []
    for stage in route["stages"]:
        if stage["kind"] != "mesh":
            continue
        ingress, egress = boundary.get(stage["from"]), boundary.get(stage["to"])
        if ingress is None or egress is None:
            return None
        candidates_in = transfer_index.get((ingress, *key), [])
        candidates_out = transfer_index.get((egress, *key), [])
        if len(candidates_in) != 1 or len(candidates_out) != 1:
            return None
        incoming, outgoing = candidates_in[0], candidates_out[0]
        forward = outgoing["start_ps"] - incoming["start_ps"]
        backward = incoming["end_ps"] - outgoing["end_ps"]
        if forward < 0 or backward < 0:
            return None
        stages.append({"kind": "mesh", "network": stage["network"],
                       "from_monitor": ingress, "to_monitor": egress,
                       "request_ps": forward, "response_ps": backward,
                       "sum_ps": forward + backward,
                       "router_links": stage["router_links"]})
    if not stages:
        return None
    terminal = boundary.get(next(s for s in reversed(route["stages"])
                                 if s["kind"] == "mesh")["to"])
    matches = transfer_index.get((terminal, *key), [])
    if len(matches) != 1:
        return None
    service = matches[0]["end_ps"] - matches[0]["start_ps"]
    if service < 0:
        return None
    total = source_tx["end_ps"] - source_tx["start_ps"]
    if sum(stage["sum_ps"] for stage in stages) + service != total:
        return None
    stages.append({"kind": "terminal_axi_service", "monitor": terminal,
                   "sum_ps": service,
                   "note": "Includes target-facing AXI model and any downstream "
                           "crossbar/service delay; not isolated device latency"})
    return stages


def _quantiles(samples):
    samples = sorted(samples)
    return {"min_ps": samples[0], "avg_ps": mean(samples),
            "max_ps": samples[-1], "median_ps": median(samples),
            "p95_ps": samples[ceil(0.95 * len(samples)) - 1]}



def _cycle_stats(samples, reference_period_ps):
    """Normalize simulated ps durations to the *measured* reference clock.

    The original picosecond data is preserved for future multi-clock paths.
    This is not a hardware frequency or a per-router latency claim.
    """
    if type(reference_period_ps) is not int or reference_period_ps <= 0:
        raise FabricReportError("positive measured reference period required")
    stats = _quantiles(samples)
    return {**stats,
            "min_cycles": stats["min_ps"] / reference_period_ps,
            "avg_cycles": stats["avg_ps"] / reference_period_ps,
            "max_cycles": stats["max_ps"] / reference_period_ps,
            "median_cycles": stats["median_ps"] / reference_period_ps}


def _display_cycles(stats, observation):
    """Keep each cell's sample count, source run, and reference period."""
    if not stats:
        return None
    return {
        "min_cycles": stats["min_cycles"],
        "avg_cycles": stats["avg_cycles"],
        "max_cycles": stats["max_cycles"],
        "n": observation["sample_count"],
        "reference_clock_period_ps": observation["clock_period_ps"],
        "run_sha": observation["source_sha"],
        "source_equivalence": observation.get("source_equivalence", "exact_sha"),
        "run_report": observation["run_report"],
    }


def latency_table(report, scope=None):
    """Source/destination rows with independent read and write stage stats.

    The newest matching-source baseline run is selected per operation. Stalled
    or historical results cannot be silently substituted for unmeasured stages.
    """
    mesh_columns = {}
    for plane in ("data", "config"):
        fabrics = {p["fabric"] for p in report["interfaces"]
                   if p["plane"] == plane and p["router"] is not None}
        def order(name):
            return (0 if name.startswith("compute") else
                    1 if name.startswith("global") else
                    2 if name.startswith("memory") else 3, name)
        mesh_columns[plane] = sorted(fabrics, key=order)
    by_route = {route["id"]: route for route in report["routes"]}
    rows = []
    for cell in report["matrix"]:
        route = by_route.get(cell["route_id"])
        mesh = {}
        target = {"read": None, "write": None}
        total = {"read": None, "write": None}
        evidence = {}
        if route:
            for o in route.get("one_beat_stage_observations", []):
                op = o["operation"]
                if (op not in ("read", "write") or
                        not o.get("matches_site_source") or op in evidence
                        or (scope is not None and o.get("fabric_scope") != scope)):
                    continue
                evidence[op] = {"n": o["sample_count"],
                                "clock_period_ps": o["clock_period_ps"],
                                "sha": o["source_sha"],
                                "run_report": o["run_report"]}
                total[op] = _display_cycles(o["end_to_end"], o)
                for stage in o["stage_metrics"]:
                    value = _display_cycles(stage["sum_stats"], o)
                    if stage["kind"] == "mesh":
                        mesh.setdefault(stage["network"], {})[op] = value
                    elif stage["kind"] == "terminal_axi_service":
                        target[op] = value
            if set(mesh).difference(route["network_path"]):
                raise FabricReportError("measured mesh absent from structural route")
        rows.append({
            "source": cell["source"], "destination": cell["target"],
            "plane": cell["plane"], "access": cell["access"],
            "route_id": cell["route_id"],
            "network_path": route["network_path"] if route else [],
            "mesh_cycles": mesh,
            "target_cycles": target,
            "end_to_end_cycles": total,
            "evidence": evidence,
        })
    eligible_periods = {o["clock_period_ps"]
                        for route in report["routes"]
                        for o in route.get("one_beat_stage_observations", [])
                        if o.get("matches_site_source")
                        and (scope is None or o.get("fabric_scope") == scope)
                        and type(o.get("clock_period_ps")) is int
                        and o["clock_period_ps"] > 0}
    common_period = next(iter(eligible_periods)) if len(eligible_periods) == 1 else None
    # Distinguish "no traffic ever captured" from "historical traffic
    # captured but not valid for this RTL/DV execution input tree". Neither
    # case may populate a current-source latency metric.
    historical = [o for route in report["routes"]
                  for o in route.get("one_beat_observations", [])
                  if not o.get("matches_site_source")
                  and (scope is None or o.get("fabric_scope") == scope)]
    accepted = [o for route in report["routes"]
                for o in route.get("one_beat_stage_observations", [])
                if o.get("matches_site_source")
                and (scope is None or o.get("fabric_scope") == scope)]
    measured_rows = sum(
        bool(r["end_to_end_cycles"]["read"] or r["end_to_end_cycles"]["write"])
        for r in rows)
    coverage = {
        "status": ("current_source_measured" if measured_rows else
                   "historical_only" if historical else "no_observations"),
        "current_measured_routes": measured_rows,
        "total_routes": sum(bool(r["route_id"]) for r in rows),
        "current_stage_observations": len(accepted),
        "historical_observations": len(historical),
        "historical_source_shas": sorted({o["source_sha"] for o in historical}),
        "note": ("Historical traces remain available in original run reports but "
                 "cannot be presented as current RTL latency; execute a fresh "
                 "source-matched serial one-beat NoC regression to refresh."),
    }
    return {
        "schema_version": 1,
        "evidence_coverage": coverage,
        "units": "simulation_reference_clock_cycles",
        "reference_clock": {
            "domain": "soc_single_clock", "signal": "clk_i",
            "measured_period_ps": common_period,
            "measured_frequency_hz": (10**12 / common_period
                                      if common_period is not None else None),
            "hardware_frequency_hz": None,
            "is_common_in_eligible_evidence": bool(common_period),
        },
        "stat_order": ["min", "avg", "max"],
        "mesh_columns": mesh_columns,
        "stage_scope": "AXI_ingress_to_egress_request_plus_response",
        "target_scope": "last_target_facing_AXI_port_includes_downstream_crossbar_and_model",
        "rows": rows,
    }



def _comparable_stage_changes(left, right):
    """Compare only stages identifying the same real passive AXI boundary.

    Missing/incomparable mesh or terminal stages are explicitly listed. They
    cannot invalidate a separately proven end-to-end comparison or fabricate
    a local-only router delta.
    """
    def index(items):
        result = {}
        for row in items:
            if row.get("kind") == "mesh":
                key = ("mesh", row.get("network"), row.get("from_monitor"),
                       row.get("to_monitor"))
            elif row.get("kind") == "terminal_axi_service":
                key = ("terminal_axi_service", row.get("monitor"))
            else:
                raise FabricReportError("unknown passive AXI stage kind")
            if None in key or key in result:
                raise FabricReportError("invalid or duplicate passive AXI stage identity")
            result[key] = row
        return result

    a, b = index(left), index(right)
    shared = []
    for key in sorted(set(a) & set(b)):
        left_stats, right_stats = a[key].get("sum_stats"), b[key].get("sum_stats")
        if not (isinstance(left_stats, dict) and isinstance(right_stats, dict)
                and type(left_stats.get("avg_cycles")) in (int, float)
                and type(right_stats.get("avg_cycles")) in (int, float)):
            raise FabricReportError("shared AXI stage lacks measured average")
        shared.append({
            "identity": list(key),
            "left_avg_cycles": left_stats["avg_cycles"],
            "right_avg_cycles": right_stats["avg_cycles"],
            "right_minus_left_cycles":
                right_stats["avg_cycles"] - left_stats["avg_cycles"],
        })
    return {
        "matched_stage_deltas": shared,
        "left_only_unmeasured_in_right": [list(k) for k in sorted(set(a) - set(b))],
        "right_only_unmeasured_in_left": [list(k) for k in sorted(set(b) - set(a))],
    }


def compare_measured_scopes(report, left_scope: str, right_scope: str) -> dict:
    """Pair source-equivalent actual one-beat samples, never infer a speedup.

    The exact generated route, selected request addresses, operation, clock
    and source case counts must match. Separate scopes without such a pair
    remain UNMEASURED; no interpolation across a missing local NoC top.
    """
    if not isinstance(left_scope, str) or not left_scope or not isinstance(right_scope, str) or not right_scope or left_scope == right_scope:
        raise FabricReportError("distinct nonempty benchmark scopes required")
    rows = []
    status_counts = defaultdict(int)
    for route in report["routes"]:
        observations = route.get("one_beat_stage_observations", [])
        for op in ("read", "write"):
            candidates = {}
            for scope in (left_scope, right_scope):
                found = [o for o in observations
                         if o.get("operation") == op and o.get("fabric_scope") == scope
                         and o.get("matches_site_source") is True]
                candidates[scope] = found
            status = "unmeasured_missing_scope"
            delta = None
            reason = "both exact-source measured route operations required"
            first, second = candidates[left_scope], candidates[right_scope]
            if len(first) > 1 or len(second) > 1:
                status = "incompatible_duplicate_evidence"
                reason = "multiple eligible observations for same route/scope/operation"
            elif first and second:
                a, b = first[0], second[0]
                allowed = {"exact_sha", "verified_same_tree", "verified_rtl_inputs"}
                # The original benchmark plan, accepted AXI actor and complete
                # selected cases must agree. Same addresses/counts alone cannot
                # qualify an arbitrary different initiator or test workload.
                baseline = "Fabric baseline: single-outstanding one-beat"
                same_inputs = (
                    a.get("source_equivalence") in allowed
                    and b.get("source_equivalence") in allowed
                    and a.get("case_provenance") ==
                        b.get("case_provenance") ==
                        "verified_complete_benchmark_plan_and_axi"
                    and a.get("source_actor") == b.get("source_actor") == route["source"]
                    and a.get("benchmark_profile") == b.get("benchmark_profile") == "unloaded"
                    and a.get("benchmark_phase") == b.get("benchmark_phase") == baseline
                    and a.get("simulator") is not None
                    and a.get("simulator") == b.get("simulator")
                    and isinstance(a.get("sample_case_ids"), list)
                    and len(a["sample_case_ids"]) == a.get("sample_count")
                    and a["sample_case_ids"] == b.get("sample_case_ids")
                    and len(set(a["sample_case_ids"])) == len(a["sample_case_ids"])
                    and isinstance(a.get("sample_case_keys"), list)
                    and a["sample_case_keys"] == b.get("sample_case_keys")
                    and a.get("sample_count") == b.get("sample_count")
                    and type(a.get("sample_count")) is int and a["sample_count"] > 0
                    and type(a.get("clock_period_ps")) is int
                    and a["clock_period_ps"] > 0
                    and a["clock_period_ps"] == b.get("clock_period_ps")
                )
                if same_inputs and a.get("end_to_end") and b.get("end_to_end"):
                    status = "measured_same_source_and_cases"
                    reason = "matched exact source-selected cases and reference clock"
                    delta = {
                        "left_avg_cycles": a["end_to_end"]["avg_cycles"],
                        "right_avg_cycles": b["end_to_end"]["avg_cycles"],
                        "right_minus_left_cycles": (
                            b["end_to_end"]["avg_cycles"] - a["end_to_end"]["avg_cycles"]),
                        "n": a["sample_count"],
                        "reference_clock_period_ps": a["clock_period_ps"],
                        "left_run_report": a["run_report"],
                        "right_run_report": b["run_report"],
                        **_comparable_stage_changes(
                            a.get("stage_metrics", []), b.get("stage_metrics", [])),
                    }
                else:
                    status = "incompatible_source_clock_or_case_set"
                    reason = "benchmark plan, actor, backend, complete cases, source or clock mismatch"
            status_counts[status] += 1
            rows.append({"route_id": route["id"], "operation": op,
                         "left_scope": left_scope, "right_scope": right_scope,
                         "status": status, "reason": reason, "comparison": delta})
    return {
        "schema_version": 1,
        "left_scope": left_scope, "right_scope": right_scope,
        "evidence": "passive_source_attested_axi_latency_not_router_or_phy_proof",
        "counts": dict(sorted(status_counts.items())),
        "rows": rows,
    }


def attach_one_beat_observations(report, entries, output, source_sha):
    """Attach source-completion timing and rigorous serial per-mesh deltas.

    Router link counts are never interpreted as cycles. Per-mesh deltas use
    tapped AXI ingress/egress. The final AXI service includes any unobserved
    downstream target crossbar; individual router/device cycles are unknown.
    """
    routes = {r["id"]: r for r in report["routes"]}
    by_source = defaultdict(list)
    target_info = {t["name"]: t for t in report["targets"]}
    for route in report["routes"]:
        route.setdefault("one_beat_stage_observations", [])
        by_source[route["source"]].append(route)

    baseline_phase = "Fabric baseline: single-outstanding one-beat"
    # Publisher index order is file-path order, not necessarily recency.
    # Newest verified run wins for each route and operation in the wide table.
    for entry in sorted(entries, key=lambda item: (item.get("recorded_at") or "",
                                                   item.get("run_id") or 0), reverse=True):
        if (not entry.get("axi") or not entry.get("passed")
                or "axi-transactions.json" not in entry.get("assets", [])):
            continue
        path = output / Path(entry["path"]).parent / "axi-transactions.json"
        trace = json.loads(path.read_text())
        run = trace["run"]
        if (not run.get("capture_bound") or run.get("capture_overflow")
                or run.get("dirty") is not False):
            continue
        rows = trace["sections"]["axi"]["transactions"]
        # Only the source-authored, fully checked benchmark plan can qualify
        # case identity. Ordinary runs still contribute historic observations
        # and may be shown as stages, but cannot prove cross-scope equivalence.
        from fabric_benchmark import validate as validate_benchmark
        benchmark_cases = {}
        bench_path = path.parent / "fabric-benchmark-plan.json"
        proof_path = path.parent / "fabric-benchmark-evidence.json"
        benchmark_profile = None
        if bench_path.is_file() or proof_path.is_file():
            if not bench_path.is_file() or not proof_path.is_file():
                raise FabricReportError("incomplete archived benchmark case proof")
            bench = json.loads(bench_path.read_text())
            proof = json.loads(proof_path.read_text())
            if (bench.get("scope") != entry["target"]
                    or bench.get("phase") != baseline_phase
                    or bench.get("profile") != "unloaded"
                    or validate_benchmark(trace, bench) != proof):
                raise FabricReportError("archived benchmark plan/capture proof mismatch")
            benchmark_profile = bench["profile"]
            for case in bench["cases"]:
                if case["warmup"]:
                    continue
                for operation in case["operations"]:
                    key = (case["monitor"], case["plane"], operation,
                           number(case["address"]))
                    if key in benchmark_cases:
                        raise FabricReportError("duplicate selected benchmark AXI case")
                    benchmark_cases[key] = f"{case['case_id']}:{operation}"
        # GitHub's tested temporary PR merge commit and the final main merge
        # commit can be different SHAs for the same exact Git tree. Accept
        # that only when the trusted collector verified both trees.
        identity = ("exact_sha" if entry["source_sha"] == source_sha else
                    "verified_same_tree" if entry.get("verified_site_source_sha") == source_sha
                    else "verified_rtl_inputs" if entry.get("verified_fabric_source_sha") == source_sha
                    else None)
        matched = defaultdict(list)
        source_samples = defaultdict(list)
        for item in rows:
            if (item.get("role") != "initiator" or item.get("status") != "complete"
                    or item.get("expected_beats") != 1 or item.get("issues")
                    or number(item.get("response") or 0) != 0
                    or item.get("latency_ps") is None
                    or item.get("start_ps") is None or item.get("end_ps") is None
                    or item["latency_ps"] != item["end_ps"] - item["start_ps"]):
                continue
            for route in by_source[item["monitor"]]:
                target = target_info[route["target"]]
                address = number(item["address"])
                if (route["plane"] == item["plane"] and
                        number(target["address_base"]) <= address <
                        number(target["address_base"]) + number(target["address_size"])):
                    matched[(route["id"], item["operation"])].append(number(item["latency_ps"]))
                    if item.get("phase") == baseline_phase:
                        source_samples[(route["id"], item["operation"])].append(item)

        for (route_id, operation), samples in matched.items():
            routes[route_id]["one_beat_observations"].append({
                "operation": operation, "count": len(samples),
                **_quantiles(samples), "source_sha": entry["source_sha"],
                "matches_site_source": identity is not None,
                "source_equivalence": identity or "historical",
                "test_scope": entry["target"],
                "fabric_scope": entry.get("fabric_scope", "unspecified"),
                "simulator": entry["engine"],
                "run_report": entry["path"],
                "scope": "initiator_end_to_end_B_or_RLAST_all_test_phases",
            })

        # Do not project stage timing from different RTL/DV execution inputs.
        # Either the SHA matches exactly or trusted collection must attest
        # identical Git trees / matching checked-in hardware and DV inputs.
        # The run must measure its own positive clock period.
        clock_ps = run.get("clock_period_ps")
        if (identity is None or
                type(clock_ps) is not int or clock_ps <= 0 or
                not source_samples):
            continue
        monitors = trace["sections"]["axi"]["monitors"]
        boundary = {}
        for monitor in monitors:
            for endpoint in monitor["endpoints"]:
                if endpoint in boundary and boundary[endpoint] != monitor["id"]:
                    raise FabricReportError(f"ambiguous AXI monitor endpoint {endpoint}")
                boundary[endpoint] = monitor["id"]
        indexed = _observed_transfers(rows, baseline_phase)
        for (route_id, operation), samples in source_samples.items():
            route = routes[route_id]
            # Require all baseline source samples to be unique under the
            # observable key, otherwise pairing could select wrong traffic.
            paired = []
            for source_tx in samples:
                source_key = (source_tx["monitor"], source_tx["plane"],
                              source_tx["operation"], number(source_tx["address"]))
                if len(indexed[source_key]) != 1:
                    continue
                components = _observed_stages(route, source_tx, indexed, boundary)
                if components is not None:
                    paired.append((source_tx, components))
            if not paired:
                continue
            # Never compute a deceptively fast subset when a slow, failed,
            # duplicate or unpaired source case was silently dropped at a tap.
            if len(paired) != len(samples):
                continue
            sample_case_ids = None
            if benchmark_cases:
                selected_keys = {
                    key for key in benchmark_cases
                    if key[0] == route["source"] and key[2] == operation
                    and key[1] == route["plane"]
                    and target_info[route["target"]]["address_base"] is not None
                    and number(target_info[route["target"]]["address_base"]) <= key[3] <
                        number(target_info[route["target"]]["address_base"]) +
                        number(target_info[route["target"]]["address_size"])
                }
                actual_keys = {
                    (tx["monitor"], tx["plane"], tx["operation"], number(tx["address"]))
                    for tx, _ in paired
                }
                if actual_keys != selected_keys or len(paired) != len(selected_keys):
                    continue
                sample_case_ids = sorted(benchmark_cases[key] for key in actual_keys)
            stage_stats = []
            for index, component in enumerate(paired[0][1]):
                metrics = ("request_ps", "response_ps", "sum_ps") if component["kind"] == "mesh" else ("sum_ps",)
                current = {k:v for k,v in component.items() if k not in metrics}
                for metric in metrics:
                    values = [row[index][metric] for _,row in paired]
                    current[metric.replace("_ps", "_stats")] = _cycle_stats(values, clock_ps)
                stage_stats.append(current)
            elapsed = [tx["latency_ps"] for tx,_ in paired]
            route["one_beat_stage_observations"].append({
                "operation": operation,
                "sample_count": len(paired), "clock_period_ps": clock_ps,
                "sample_case_keys": sorted(
                    f"{tx['monitor']}:{tx['plane']}:{tx['operation']}:"
                    f"{number(tx['address']):x}" for tx, _ in paired),
                "sample_case_ids": sample_case_ids,
                "case_provenance": (
                    "verified_complete_benchmark_plan_and_axi" if sample_case_ids
                    else "untagged_legacy_axi_stage_samples"),
                "source_actor": route["source"],
                "benchmark_profile": benchmark_profile,
                "benchmark_phase": baseline_phase,
                "end_to_end": _cycle_stats(elapsed, clock_ps),
                "stage_metrics": stage_stats,
                "source_sha": entry["source_sha"], "matches_site_source": True,
                "source_equivalence": identity,
                "test_scope": entry["target"],
                "fabric_scope": entry.get("fabric_scope", "unspecified"),
                "simulator": entry["engine"],
                "run_report": entry["path"],
                "scope": "serial_single_outstanding_AXI_tap_boundary_deltas",
            })
    report["latency_table"] = latency_table(report)
    eligible_scopes = sorted({
        o["fabric_scope"] for route in report["routes"]
        for o in route.get("one_beat_stage_observations", [])
        if o.get("matches_site_source")
    })
    report["latency_scopes"] = {
        scope: latency_table(report, scope=scope) for scope in eligible_scopes
    }
    # Publish real compatibility only for scopes that actually produced
    # source-verified samples. Missing standalone local RTL stays unmeasured.
    report["latency_scope_comparisons"] = [
        compare_measured_scopes(report, a, b)
        for i, a in enumerate(eligible_scopes)
        for b in eligible_scopes[i+1:]
    ]
    return report


def load(root=ROOT):
    from interface_contracts import build as resolve_contracts
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    knobs = yaml.safe_load((root / "config/interface_contracts.yaml").read_text())
    noc_root = root / "gen/noc/floonoc"
    noc_manifest = json.loads((noc_root / "manifest.json").read_text())
    networks = prepare_networks(noc_manifest, noc_root)
    resolved = resolve_contracts(soc, knobs, networks["global_data"]["profile"])
    super_manifest = json.loads((root / "gen/supernoc/manifest.json").read_text())
    chip_manifest = json.loads((root / "gen/chip/manifest.json").read_text())
    return build(soc, knobs, noc_manifest, networks, super_manifest,
                 chip_manifest, resolved["ports"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.dumps(load(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
    else:
        print(data)


if __name__ == "__main__":
    main()
