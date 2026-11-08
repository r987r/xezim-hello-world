"""Independent #34 GMII -> real DDR -> PULP iDMA -> PCIe/TX RTL scoreboard.

The verified values come from a real external GMII frame, CPU-owned RTL CQ
and byte checks, modeled RC BAR readback, passive AXI channel observations,
and real LiteDRAM DFI/BankModel events. This checker NEVER drives an AXI or
memory model, invents a completion, or combines separate regression runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from dv.common.selected_aperture import selected_aperture


def check_accepted_axi(plan_path: Path) -> dict[str, int]:
    """Require accepted real initiator traffic at each composite boundary."""
    plan_path = Path(plan_path)
    eth, eth_size = selected_aperture("ethernet0.sram", "data", plan_path=plan_path)
    ctrl, ctrl_size = selected_aperture("ethernet0.ctrl", "config", plan_path=plan_path)
    ddr, ddr_size = selected_aperture("memory0.ddr0", "data", plan_path=plan_path)
    pcie, pcie_size = selected_aperture("pcie0.sram", "data", plan_path=plan_path)
    peer, peer_size = selected_aperture("compute1.sram", "data", plan_path=plan_path)
    if not (eth_size >= 0x2200 and ctrl_size >= 0x100 and
            ddr_size >= 0x2000 and pcie_size >= 0x700 and peer_size >= 0x2100):
        raise AssertionError("selected composite memory apertures too small")
    checks = {
        "cpu_queue_config": ("compute0_local_config.cpu", "aw", ctrl, 0x100),
        "cpu_descriptor_writes": ("compute0_local_data.cpu", "aw", eth + 0x1000, 0x620),
        "cpu_completion_reads": ("compute0_local_data.cpu", "ar", eth + 0x1200, 0x420),
        "eth_rx_descriptor_fetch": ("ethernet0_local_data.packet_dma", "ar", eth + 0x1000, 0x20),
        "eth_rx_to_ddr": ("ethernet0_local_data.packet_dma", "aw", ddr + 0x1000, 0x100),
        "idma_reads_ddr": ("compute0_local_data.dma", "ar", ddr + 0x1000, 0x100),
        "idma_writes_pcie_stage": ("compute0_local_data.dma", "aw", pcie + 0x600, 0x100),
        "idma_writes_eth_tx": ("compute0_local_data.dma", "aw", eth + 0x2100, 0x100),
        "idma_writes_cpu_readback": ("compute0_local_data.dma", "aw", peer + 0x2000, 0x100),
        "eth_tx_payload_fetch": ("ethernet0_local_data.packet_dma", "ar", eth + 0x2100, 0x100),
    }
    counts = {label: 0 for label in checks}
    counts.update({"eth_packet_b": 0, "idma_b": 0})
    file = plan_path.parent / "axi-events.jsonl"
    if not file.is_file() or file.is_symlink():
        raise AssertionError("missing same-run passive AXI event capture")
    from tools.axi_report import read_events
    events, issues = read_events(file)
    if issues:
        raise AssertionError(f"invalid/incomplete accepted AXI capture: {issues[:3]}")
    for event in events:
        monitor, channel = event.get("monitor"), event.get("channel")
        if monitor == "ethernet0_local_data.packet_dma" and channel == "b":
            counts["eth_packet_b"] += 1
        if monitor == "compute0_local_data.dma" and channel == "b":
            counts["idma_b"] += 1
        if channel not in ("aw", "ar"):
            continue
        try:
            address = int(event.get("fields", {})["addr"], 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise AssertionError("AXI handshake lacked physical address") from exc
        for label, (who, wanted, start, length) in checks.items():
            if monitor == who and channel == wanted and start <= address < start + length:
                counts[label] += 1
    missing = sorted(name for name, count in counts.items() if not count)
    if missing:
        raise AssertionError(f"one-run passive AXI paths unobserved: {missing}; counts={counts}")
    return counts


def verify_controller(dd, probe_counts: dict[str, int]) -> dict[str, int]:
    """Actual LiteDRAM AXI/DFI and behavioral bank storage, never modeled AXI RAM."""
    counters = {
        "controller_axi_aw": int(dd.controller_axi_aw_count.value),
        "controller_axi_b": int(dd.controller_axi_b_count.value),
        "controller_axi_ar": int(dd.controller_axi_ar_count.value),
        "controller_axi_rlast": int(dd.controller_axi_rlast_count.value),
        "dfi_read": int(dd.dfi_read_count.value),
        "dfi_write": int(dd.dfi_write_count.value),
        "bank_storage_write": int(dd.bank_storage_write_count.value),
        "captured_dfi_read": probe_counts.get("dfi_read", 0),
        "captured_dfi_write": probe_counts.get("dfi_write", 0),
        "captured_storage_write": probe_counts.get("bankmodel_storage_write", 0),
    }
    if (int(dd.ddr_init_done_o.value) != 1 or
            int(dd.ddr_init_error_o.value) != 0 or
            not all(value > 0 for value in counters.values()) or
            counters["controller_axi_aw"] != counters["controller_axi_b"] or
            counters["controller_axi_ar"] != counters["controller_axi_rlast"]):
        raise AssertionError(f"real controller/DFI/captured bank evidence failed: {counters}")
    return counters


def write_pass(path: Path, plan: dict, axi: dict, ddr: dict, tlp: dict,
               frame: bytes) -> None:
    """Only after ALL independent evidence passes in the SAME cocotb run."""
    if not frame or any(not value for value in (axi, ddr, tlp)):
        raise AssertionError("cannot publish unmeasured composite PASS")
    output = {
        "schema_version": 1,
        "scope": "one_rtl_simulation_real_ethernet_real_litedram_real_idma_modeled_pcie_rc",
        "status": "pass",
        "source_identity_sha256": plan["identity"]["identity_sha256"],
        "target": plan["target"],
        "selected_seed": plan["seed"],
        "gmii_frame_hex": frame.hex(),
        "gmii_frame_bytes": len(frame),
        "axi_accepted_counts": axi,
        "real_controller_and_behavioral_dfi": ddr,
        "tlp_accepted_counts": tlp,
        "ddr_physical_phy": "not_modeled",
        "pcie_phy": "modeled_no_LTSSM",
        "pcie_host_memory_outbound_dma": "not_claimed",
        "ethernet_rx_queues": 1,
        "one_run_only": True,
    }
    destination = Path(path)
    if destination.exists() or destination.is_symlink():
        raise AssertionError("refusing to replace preexisting combined scoreboard")
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
