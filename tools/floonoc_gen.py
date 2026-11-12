#!/usr/bin/env python3
"""Generate *actual upstream FlooGen RTL* for all SoC NoC instances.

Source of truth: config/soc.yaml + config/interface_contracts.yaml.
Do not duplicate hand-authored FlooGen YAML; it is materialized alongside
each generated NoC's SystemVerilog. Third-party FlooNoC/AXI/common_cells
implementation RTL stays in immutable, pinned upstream checkouts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml
from subsystem_fabric import peripherals

ROOT = Path(__file__).resolve().parents[1]
FLOO_COMMIT = yaml.safe_load((ROOT / "config/ip.lock.yaml").read_text())["third_party"]["floonoc"]["commit"]
NATIVE = {"MaxTxns", "MaxTxnsPerId", "MaxUniqueIds", "AtopSupport", "MaxAtomicTxns", "RRoBType", "BRoBType",
          "RRoBSize", "BRoBSize"}
ROBS = {"NoRoB", "SimpleRoB", "NormalRoB"}


class NoCGenerationError(ValueError):
    pass


def integer(value, label):
    if type(value) is not int or not 1 <= value <= 256:
        raise NoCGenerationError(f"{label}: positive integer <=256 required")
    return value


def mapped_regions(soc, plane):
    regions = {}
    for item in soc["address_map"][plane]:
        addr = int(item["base"], 0)
        size = int(item["size"], 0)
        if addr < 0 or size <= 0:
            raise NoCGenerationError(f"invalid range for {item['name']}")
        regions[item["name"]] = {"base": addr, "size": size}
    return regions


def profile(name, plane, mgrs, targets, soc, knobs):
    """FlooGen upstream network schema with named endpoints and XY links."""
    if plane not in ("data", "config"):
        raise NoCGenerationError("invalid NoC plane")
    bus = soc["buses"][plane]
    if plane == "data":
        in_id = bus["id_bits"]
        out_id = bus["id_bits"]
        if name == "global_data":
            in_id += (2 - 1).bit_length()  # CPU and DMA behind local compute NoC
        elif name.endswith("_local_data") and name not in {
                s["name"] + "_local_data" for s in soc["subsystems"] if s["type"] == "memory"}:
            out_id += (2 - 1).bit_length()
    else:
        # AXI-Lite signals are converted at the boundary to AXI4, one beat.
        # The wire transport is 32-bit AXI4, NOT native AXI4-Lite.
        in_id, out_id = 1, 1
    protocols = [
        {"name": "axi_in", "type": "narrow", "protocol": "AXI4",
         "data_width": bus["data_bits"], "addr_width": bus["addr_bits"],
         "id_width": in_id, "user_width": 1, "type_prefix": None},
        {"name": "axi_out", "type": "narrow", "protocol": "AXI4",
         "data_width": bus["data_bits"], "addr_width": bus["addr_bits"],
         "id_width": out_id, "user_width": 1, "type_prefix": None}
    ]
    endpoints = [{"name": x, "mgr_port_protocol": ["axi_in"]} for x in mgrs]
    for target, windows in targets:
        if not windows:
            raise NoCGenerationError(f"{name}.{target} has no address ranges")
        endpoints.append({
            "name": target, "sbr_port_protocol": ["axi_out"],
            "addr_range": copy.deepcopy(windows[0] if len(windows) == 1 else windows)
        })
    if len({e["name"] for e in endpoints}) != len(endpoints):
        raise NoCGenerationError(f"{name} duplicates endpoint names")
    if len(endpoints) < 2:
        raise NoCGenerationError(f"{name} must have at least two endpoints")
    # One NI per router/ejection position avoids unsupported multiple
    # endpoint-to-Eject assignments. This scales with new subsystems.
    xdim = max(2, math.ceil(math.sqrt(len(endpoints))))
    ydim = math.ceil(len(endpoints) / xdim)
    connections = [
        {"src": e["name"], "dst": "router",
         "dst_idx": [i % xdim, i // xdim], "dst_dir": "Eject"}
        for i, e in enumerate(endpoints)
    ]
    return {
        "name": "xezim_" + name,
        "description": f"Xezim {name}: independent {plane} FlooNoC from SoC config",
        "network_type": "axi",
        "routing": {"route_algo": "XY", "use_id_table": True},
        "protocols": protocols,
        "endpoints": endpoints,
        "routers": [{"name": "router", "array": [xdim, ydim],
                     "degree": 5}],
        "connections": connections
    }


def profiles(soc, knobs):
    """Config-derived network profiles; do not add TB per bridge."""
    regions_data = mapped_regions(soc, "data")
    regions_config = mapped_regions(soc, "config")
    computes = [x["name"] for x in soc["subsystems"] if x["type"] == "compute"]
    memories = [x["name"] for x in soc["subsystems"] if x["type"] == "memory"]
    peripheral_specs = peripherals(soc)
    io = [x["name"] for x in peripheral_specs]
    compute_like = computes + io
    if len(memories) != 1 or not computes:
        raise NoCGenerationError("memory model currently supports exactly one memory subsystem")
    memory = memories[0]
    for k in ("global_data", "global_config", "local_data",
              "local_config", "memory_local_data"):
        if soc["fabrics"][k]["backend"] != "floonoc":
            raise NoCGenerationError(f"FlooNoC selected architecture expects {k}.backend=floonoc")
    if soc["fabrics"]["memory_data"]["backend"] != "verilog_axi":
        raise NoCGenerationError("tested internal memory crossbar must remain Verilog AXI")
    if set(soc["networks"]["global_config"]["reachable_subsystems"]) != set(compute_like + memories):
        raise NoCGenerationError("global config must reach all named subsystems")
    memory_outputs = soc["networks"]["global_data"]["outputs"]
    for m in memory_outputs:
        if m["target"] not in regions_data:
            raise NoCGenerationError(f"memory NoC output {m['name']} has unknown destination")
    cfg_owned = {c: [] for c in compute_like + memories}
    for name, addr in regions_config.items():
        owner = soc["boot"]["primary"] if name.startswith("boot.") else name.split(".")[0]
        if owner not in cfg_owned:
            raise NoCGenerationError(f"config window {name} has no subsystem owner")
        cfg_owned[owner].append(addr)
    if not cfg_owned[memory]:
        raise NoCGenerationError("memory subsystem needs a config register aperture")
    result = {}

    def add(name, plane, initiators, sinks, family, path):
        if name in result:
            raise NoCGenerationError(f"duplicate NoC {name}")
        if family not in knobs["fabric_parameters"]:
            raise NoCGenerationError(f"missing native FlooNoC knobs for {family}")
        params = knobs["fabric_parameters"][family]
        if set(params) != NATIVE:
            raise NoCGenerationError(f"{family} native FlooNoC keys must be {sorted(NATIVE)}")
        for k, v in params.items():
            if k.endswith("Type"):
                if v not in ROBS:
                    raise NoCGenerationError(f"unsupported FlooNoC reorder type {v}")
            elif k == "AtopSupport":
                if type(v) is not bool:
                    raise NoCGenerationError(f"{family}.AtopSupport must be bool")
            elif k == "MaxAtomicTxns":
                if type(v) is not int or not 0 <= v <= 256:
                    raise NoCGenerationError(f"{family}.MaxAtomicTxns must be 0..256")
            else:
                integer(v, f"{family}.{k}")
        # The selected interfaces do not issue AXI ATOPs. The pinned
        # upstream floo_meta_buffer requires MaxAtomicTxns=0 whenever
        # AtopSupport is disabled (NoAtomicTxns assertion). Keep a full
        # non-atomic ID namespace instead of silently reducing MaxUniqueIds.
        if params["AtopSupport"] or params["MaxAtomicTxns"] != 0:
            raise NoCGenerationError(
                f"{name}: ATOPs unsupported; use AtopSupport=false, MaxAtomicTxns=0")
        max_ids = 1 << (1 if plane == "config" else soc["buses"]["data"]["id_bits"])
        if params["MaxUniqueIds"] > max_ids:
            raise NoCGenerationError(f"{name}: MaxUniqueIds exceeds AXI destination ID width")
        # The pinned upstream floo_rob_status_table declares the usage
        # counter as clog2(MaxTxnsPerId), while cc_fifo exports
        # clog2(Depth+1). Power-of-two depths break its instance-array
        # connection. Reject this upstream corner until explicitly fixed.
        depth = params["MaxTxnsPerId"]
        if (params["BRoBType"] != "NoRoB" or params["RRoBType"] != "NoRoB"):
            if depth < params["MaxTxns"]:
                raise NoCGenerationError(f"{name}: per-ID FIFO depth below MaxTxns")
            if depth & (depth - 1) == 0:
                raise NoCGenerationError(
                    f"{name}: upstream RoB FIFO usage width mismatch at power-of-two MaxTxnsPerId")
        result[name] = {
            "path": path, "plane": plane, "family": family,
            "native_parameters": copy.deepcopy(params),
            "config": profile(name, plane, initiators, sinks, soc, knobs)
        }

    remote_data = [regions_data[n + ".sram"] for n in compute_like]
    hbm_ddr = [regions_data[x["target"]] for x in memory_outputs]
    # Main global data NoC terminates on both compute SRAM apertures too:
    # CPU0's bus-based cold boot must be able to copy code into CPU1 SRAM.
    global_data_sinks = [(c + "_sram", [regions_data[c + ".sram"]])
                         for c in compute_like]
    global_data_sinks.extend((x["name"], [regions_data[x["target"]]])
                             for x in memory_outputs)
    add("global_data", "data", compute_like, global_data_sinks,
        "global_data", "global_data")

    # AXI4 transport for AXI-Lite register accesses. Each remote
    # subsystem exposes its own (possibly disjoint) config windows.
    add("global_config", "config", compute_like,
        [(c + "_regs", cfg_owned[c]) for c in compute_like + memories],
        "global_config", "global_config")

    for comp in computes:
        # All reachable remote peripheral SRAMs belong on the local-global
        # egress. Restricting this list to compute SRAMs made CPU0->PCIe0
        # traffic raise FlooNoC DecodeError even though global_data knew it.
        other = [regions_data[c + ".sram"] for c in compute_like if c != comp]
        own_sram = regions_data[comp + ".sram"]
        cpu_sinks = [("sram", [own_sram]),
                     ("global_out", other + hbm_ddr)]
        if comp == soc["boot"]["primary"]:
            cpu_sinks += [
                ("boot_rom", [regions_data["boot.rom"]]),
                ("boot_flash", [regions_data["boot.flash"]])
            ]
        add(comp + "_local_data", "data",
            ["cpu", "dma", "global_in"], cpu_sinks,
            "local_data", comp + "/local_data")
        targets = [("dma_regs", [regions_config[comp + ".dma"]])]
        if comp == soc["boot"]["primary"]:
            targets.append(("reset_ctrl", [regions_config["boot.reset_ctrl"]]))
        distant_cfg = [value for name in compute_like + memories if name != comp
                       for value in cfg_owned[name]]
        targets.append(("global_out", distant_cfg))
        add(comp + "_local_config", "config", ["cpu", "global_in"],
            targets, "local_config", comp + "/local_config")

    # Generic peripheral topology: local data + independent config NoC.
    for sub in peripheral_specs:
        name = sub["name"]
        own = regions_data[name + ".sram"]
        others = [regions_data[c + ".sram"] for c in compute_like if c != name]
        add(name + "_local_data", "data",
            [sub["data_initiator"], "global_in"],
            [("sram", [own]), ("global_out", others + hbm_ddr)],
            "local_data", name + "/local_data")
        distant_cfg = [v for owner in compute_like + memories if owner != name
                       for v in cfg_owned[owner]]
        add(name + "_local_config", "config",
            [sub["config_initiator"], "global_in"],
            [("controller_regs", cfg_owned[name]), ("global_out", distant_cfg)],
            "local_config", name + "/local_config")

    # Memory-local NoC has TWO separate upstream ingress managers feeding
    # the existing, already-tested crossbar. FlooNoC does not replace that
    # internal crossbar or pretend the HBM/DDR models are physical controllers.
    add(memory + "_local_data", "data",
        [x["name"] for x in memory_outputs],
        [("target_crossbar", hbm_ddr)], "memory_local_data",
        memory + "/local_data")
    add(memory + "_local_config", "config", ["global_in"],
        [("controller_regs", cfg_owned[memory])], "local_config",
        memory + "/local_config")

    if len(result) != 2 + 2 * len(compute_like) + 2 * len(memories):
        raise NoCGenerationError("NoC count mismatch")
    return result


def native_bindings(top, params):
    """Only replace the upstream *chimney parameter expression*.

    No router, routing algorithm or AXI module is rewritten. Drift in the
    upstream FlooGen generated template fails closed, avoiding silent knobs.
    """
    search = ".ChimneyCfg(set_ports(ChimneyDefaultCfg,"
    count = top.count(search)
    if count == 0 or "floo_axi_chimney" not in top:
        raise NoCGenerationError("FlooGen output changed: chimney override anchor missing")
    fields = [
        f"    c.MaxTxns = {params['MaxTxns']};",
        f"    c.MaxUniqueIds = {params['MaxUniqueIds']};",
        f"    c.MaxTxnsPerId = {params['MaxTxnsPerId']};",
        f"    c.BRoBType = {params['BRoBType']};",
        f"    c.BRoBSize = {params['BRoBSize']};",
        f"    c.RRoBType = {params['RRoBType']};",
        f"    c.RRoBSize = {params['RRoBSize']};",
    ]
    body = ("\n  // Derived from config/interface_contracts.yaml. Upstream chimney RTL unchanged.\n"
            "  function automatic chimney_cfg_t xezim_chimney_cfg();\n"
            "    chimney_cfg_t c;\n"
            "    c = ChimneyDefaultCfg;\n" + "\n".join(fields) +
            "\n    return c;\n  endfunction\n")
    at = top.index(");") + 2
    # In FlooGen's structural top, this is the first module-port close.
    result = top[:at] + body + top[at:]
    replacement = (
        f".AtopSupport(1'b{1 if params['AtopSupport'] else 0}),\n"
        f"    .MaxAtomicTxns({params['MaxAtomicTxns']}),\n"
        "    .ChimneyCfg(set_ports(xezim_chimney_cfg(),"
    )
    result = result.replace(search, replacement)
    # Upstream floo_pkg::set_ports(cfg, en_sbr, en_mgr) declares
    # manager_port=0 for target-only NIs. floo_axi_chimney asserts
    # NoMgrPortRobType if either RoB is enabled on such a port.
    # Keep the configured RoBs on initiator NIs, but use NoRoB on
    # target-only NIs. No custom router, AXI BFM, or upstream patch.
    role_target = ".ChimneyCfg(set_ports(xezim_chimney_cfg(), 1'b1, 1'b0))"
    role_source = ".ChimneyCfg(set_ports(xezim_chimney_cfg(), 1'b0, 1'b1))"
    target_count = result.count(role_target)
    source_count = result.count(role_source)
    if source_count + target_count != count:
        raise NoCGenerationError(
            "FlooGen NI port roles changed: expected sbr-only or mgr-only chimney")
    if target_count:
        role_body = (
            "\n  // EnMgrPort=0: upstream NoMgrPortRobType requires NoRoB.\n"
            "  function automatic chimney_cfg_t xezim_chimney_cfg_no_mgr();\n"
            "    chimney_cfg_t c;\n"
            "    c = xezim_chimney_cfg();\n"
            "    c.BRoBType = NoRoB;\n"
            "    c.RRoBType = NoRoB;\n"
            "    return c;\n"
            "  endfunction\n"
        )
        # Append the target-only cfg function after the shared function.
        tail = "    return c;\n  endfunction\n"
        if result.count(tail) != 1:
            raise NoCGenerationError("generated native config function anchor changed")
        result = result.replace(tail, tail + role_body, 1)
        result = result.replace(
            role_target,
            ".ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(), 1'b1, 1'b0))"
        )
    if (result.count(".ChimneyCfg(set_ports(xezim_chimney_cfg(),") != source_count or
            result.count(".ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(),") != target_count or
            result.count(".AtopSupport(1'b0)") != count or
            result.count(".MaxAtomicTxns(0)") != count):
        raise NoCGenerationError("not every chimney received role-correct native knobs")
    return result, count


def generate_all(soc, knobs, out, floogen_bin="floogen"):
    designs = profiles(soc, knobs)
    index = {"generator": "upstream FlooGen", "generator_commit": FLOO_COMMIT,
             "verification": {"generation_is_not_verification": True,
                              "routed_axi_command": "make dv-supernoc",
                              "xezim_compile_command": "python3 tools/regress.py compatibility"},
             "networks": {}}
    for name, item in sorted(designs.items()):
        root = out / item["path"]
        root.mkdir(parents=True, exist_ok=True)
        cfg_path = root / "floogen.yaml"
        cfg_path.write_text(yaml.safe_dump(item["config"], sort_keys=False))
        cmd = [floogen_bin, "rtl", "-c", str(cfg_path), "-o", str(root), "--no-format"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode:
            raise NoCGenerationError(f"upstream FlooGen failed for {name}: {proc.stderr[-4000:]}")
        base = "floo_xezim_" + name + "_noc"
        pkg = root / (base + "_pkg.sv")
        top = root / (base + ".sv")
        if not pkg.is_file() or not top.is_file():
            raise NoCGenerationError(f"upstream FlooGen missing actual RTL files for {name}")
        rtl = top.read_text()
        if "floo_axi_router" not in rtl or "floo_axi_chimney" not in rtl:
            raise NoCGenerationError(f"missing actual routers/network interfaces: {name}")
        rtl, num_nis = native_bindings(rtl, item["native_parameters"])
        # Annotate only our generated copies: upstream FlooGen is pinned and immutable.
        # A new upstream timescale policy must be reviewed rather than doubled.
        for artifact, body in ((top, rtl), (pkg, pkg.read_text())):
            if re.search(r"(?m)^\s*`timescale\b", body):
                raise NoCGenerationError(f"upstream FlooGen time scale changed: {artifact.name}")
            artifact.write_text("`timescale 1ns/1ps\n" + body)
        index["networks"][name] = {
            "subdirectory": item["path"], "plane": item["plane"],
            "top_module": base, "top": top.relative_to(out).as_posix(),
            "package": pkg.relative_to(out).as_posix(),
            "config": cfg_path.relative_to(out).as_posix(),
            "routers": math.prod(item["config"]["routers"][0]["array"]),
            "endpoint_count": len(item["config"]["endpoints"]),
            "network_interfaces_with_native_knobs": num_nis,
            "native_parameters": item["native_parameters"],
            "status": "real_upstream_structural_RTL",
        }
    (out / "manifest.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/soc.yaml")
    parser.add_argument("--knobs", type=Path, default=ROOT / "config/interface_contracts.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "gen/noc/floonoc")
    parser.add_argument("--floogen-bin", default="floogen")
    args = parser.parse_args()
    try:
        soc = yaml.safe_load(args.config.read_text())
        knobs = yaml.safe_load(args.knobs.read_text())
        index = generate_all(soc, knobs, args.out, args.floogen_bin)
        print(f"PASS upstream FlooGen: {len(index['networks'])} networks, "
              f"{sum(n['routers'] for n in index['networks'].values())} router instances")
    except (NoCGenerationError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"FlooGen integration error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
