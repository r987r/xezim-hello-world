"""Real iDMA0/iDMA1 -> generated local/global FlooNoCs -> SRAM/DDR/HBM.

This is a separate reset-isolated hardware regression. CPUs are held in
reset and CPU0's data/config NoC interfaces are driven by cocotb
**CPU0 AXI BFMs** solely to prepare DMA-only SRAM and submit 32-bit CSRs.
These are simulation initiators, NOT PCIe or an off-chip host.
The independently required cold-boot regression remains unpreloaded.
"""
from pathlib import Path
from collections import Counter
import json
import os
import yaml
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster
from dv.common.dma_vectors import build_dma_vector
from dv.common.axi_trace import attach_observers, trace_phase
from tools.axi_report import correlate, read_events

ROOT = Path(__file__).resolve().parents[2]


async def bounded(coro, what, timeout=250):
    try:
        return await with_timeout(coro, timeout, "us")
    except cocotb.result.SimTimeoutError as exc:
        raise AssertionError(f"AXI timeout during {what}") from exc


async def check_ok(resp, what):
    assert resp.resp == 0, f"{what}: unexpected AXI response {resp.resp}"


async def prep_sram(cpu0_data_bfm, case):
    """Seed only dedicated DMA descriptors/payloads via real NoC AXI writes.

    No CPU core performs 2,400 slow individual stores. Writes are split into
    16-beat/128-byte bursts, matching FlooNoC's configured burst capacity.
    """
    meta = case.manifest
    src = case.source_sram
    base = meta["source_sram_base"]
    desc = meta["descriptor_pool_start"]-base
    payload = meta["source_pool_start"]-base
    sections = [(desc, 32*meta["descriptor_count"]),
                (payload, meta["descriptor_count"]*meta["copies"][0]["length"])]
    for offset, size in sections:
        for p in range(0, size, 128):
            block = src[offset+p:offset+min(p+128, size)]
            res = await bounded(cpu0_data_bfm.write(base+offset+p, block), "CPU0 AXI BFM SRAM preload")
            await check_ok(res, "SRAM preload")


async def write_word(cpu0_config_bfm, addr, value):
    resp = await bounded(cpu0_config_bfm.write(addr, value.to_bytes(4, "little")),
                         f"CSR write {addr:#x}")
    await check_ok(resp, f"CSR write {addr:#x}")


async def read_word(cpu0_config_bfm, addr):
    resp = await bounded(cpu0_config_bfm.read(addr, 4), f"CSR read {addr:#x}")
    await check_ok(resp, f"CSR read {addr:#x}")
    return int.from_bytes(resp.data, "little")


def summarize_accepted_axi(dut, compute):
    """Read passive handshake evidence, not inferred VALID or raw monitor edges.

    Cocotbext AXI channel monitors emit only accepted VALID/READY handshakes.
    A valid RLAST without RREADY is NOT a completed AXI read.
    """
    plan = os.environ.get("SOC_RUN_PLAN")
    if not plan:
        dut._log.warning("No SOC_RUN_PLAN; cannot summarize AXI handshakes")
        return
    path = Path(plan).parent/"axi-events.jsonl"
    if not path.is_file():
        dut._log.warning("No AXI events yet at %s", path)
        return
    observed = (compute+"_local_data.dma", compute+"_local_data.sram",
                compute+"_local_data.global_out",
                "memory0_local_data.target_crossbar",
                compute+"_local_config.dma_regs")
    events = {name:Counter() for name in observed}
    last_ps = {name:0 for name in observed}
    for line in path.read_text().splitlines():
        event=json.loads(line)
        target=event.get("monitor")
        if target not in events:
            continue
        channel=event.get("channel")
        events[target][channel]+=1
        if channel=="r" and event["fields"].get("last")=="0x1":
            events[target]["rlast"]+=1
        last_ps[target]=max(last_ps[target],event["time_ps"])
    for name in observed:
        dut._log.error(
            "DMA accepted-AXI snapshot %-42s AW=%d W=%d B=%d AR=%d R=%d RLAST=%d last_ns=%d",
            name, events[name]["aw"], events[name]["w"], events[name]["b"],
            events[name]["ar"], events[name]["r"], events[name]["rlast"],
            last_ps[name]//1000)

    # Reuse the existing AXI report transaction correlator (same logic as
    # the published explorer) to identify *accepted but unretired* AR/B
    # operations. Some cross-NoC IDs are remapped, so compare per-boundary
    # progress rather than assuming IDs are globally stable.
    catalog=json.loads((ROOT/"gen/supernoc/axi_monitors.json").read_text())
    accepted, parse_issues=read_events(path)
    rows, correlation_issues, _ = correlate(accepted, catalog)
    for issue in (parse_issues+correlation_issues)[:10]:
        dut._log.error("AXI trace/correlation issue: %s", issue)
    for name in observed:
        waiting = [row for row in rows
                   if row["monitor"]==name and row["status"]=="incomplete"]
        if waiting:
            dut._log.error("DMA stalled %s: %d accepted requests still pending",
                           name, len(waiting))
            for row in waiting[:10]:
                dut._log.error(
                    "  pending %-5s ID=%s ADDR=%s beats=%d/%d start_ns=%d",
                    row["operation"], row["axi_id"], row["address"],
                    len(row["beats"]), row["expected_beats"],
                    row["start_ps"]//1000)


@cocotb.test(timeout_time=15, timeout_unit="ms")
async def two_compute_dmas_through_all_fabrics(dut):
    cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
    mem = json.loads((ROOT/"gen/chip/manifest.json").read_text())
    computes = [s["name"] for s in cfg["subsystems"] if s["type"]=="compute"]
    assert mem["dma_engines_instantiated"] == len(computes) == 2
    dut.rst_ni.value = 0
    dut.clk_i.value = 0
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk_i, 10, "ns").start())
    # Explicit CPU0 AXI BFM data/config interfaces drive the real NoC manager
    # ports in DmaTestMode;
    # all CPUs are held in reset, and the actual DMA owns its distinct port.
    cpu0_data_bfm = AxiMaster(AxiBus.from_prefix(dut, "cpu0_data_bfm"),
                              dut.clk_i, dut.rst_ni, reset_active_level=False)
    cpu0_config_bfm = AxiMaster(AxiBus.from_prefix(dut, "cpu0_config_bfm"),
                                dut.clk_i, dut.rst_ni, reset_active_level=False)
    for _ in range(15):
        await FallingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    for _ in range(8):
        await RisingEdge(dut.clk_i)

    scenario_path = os.environ.get("SOC_SCENARIO_PLAN")
    if scenario_path:
        from dv.common.scenario_dma import (
            execute_bfm_roundtrip, load_contract_from_plan)
        contract = load_contract_from_plan(Path(scenario_path))
        # This is a *different opt-in regression*, not a replacement for
        # the two-engine 105-descriptor HBM/DDR baseline below.
        await execute_bfm_roundtrip(dut, cpu0_data_bfm, cpu0_config_bfm,
                                    contract)
        # Give the passive VALID/READY capture callbacks time to settle
        # before reading the independent source-side AXI event stream.
        await Timer(1, units="us")
        plan_file = os.environ.get("SOC_RUN_PLAN")
        assert plan_file, "SCN-2 needs canonical regression monitor plan"
        raw = Path(plan_file).parent/"axi-events.jsonl"
        assert raw.is_file(), "SCN-2 missing passive real NoC AXI capture"
        from tools.axi_report import read_events
        events, issues = read_events(raw)
        assert not issues, f"SCN-2 invalid AXI stream: {issues[:3]}"
        observed = {"src_ar": 0, "ddr_aw": 0, "ddr_ar": 0,
                    "return_aw": 0}
        for event in events:
            if (event.get("monitor") != "compute0_local_data.dma"
                    or event.get("channel") not in ("ar", "aw")):
                continue
            phys = int(event["fields"]["addr"], 0)
            for label, channel, start in (
                ("src_ar", "ar", contract["source_phys"]),
                ("ddr_aw", "aw", contract["ddr_phys"]),
                ("ddr_ar", "ar", contract["ddr_phys"]),
                ("return_aw", "aw", contract["return_phys"]),
            ):
                if event["channel"] == channel and start <= phys < start + contract["length"]:
                    observed[label] += 1
        assert all(observed.values()), (
            f"SCN-2 BFM has no independently accepted full-NoC DMA traffic: {observed}")
        evidence = {"scenario_id": contract["scenario_id"],
                    "plan_sha256": contract["plan_sha256"],
                    "profile": "reset_isolated_cocotb_bfm",
                    "execution_state": "rtl_observed",
                    "observed_dma_axi_counts": observed,
                    "independently_readback_bytes": contract["length"],
                    "intent_is_not_evidence": True}
        (Path(plan_file).parent/"scenario-execution.json").write_text(
            json.dumps(evidence, sort_keys=True, indent=2)+"\n")
        dut._log.info("PASS chipdma: scenario BFM real full-NoC DDR roundtrip, %s", observed)
        return

    # First prove low-concurrency routed completion on each engine; only
    # then exercise the 100-descriptor stress chain from shared SRAM.
    checks = [
        (computes[0], "memory0.ddr0", 1, 64),
        (computes[1], "memory0.hbm0", 4, 64),
        (computes[0], "memory0.ddr0", 100, 64),
    ]
    csr_by_name = {r["name"]: int(r["base"],0)
                   for r in cfg["address_map"]["config"]}
    for stage, (compute, target, count, nbytes) in enumerate(checks):
        i = computes.index(compute)
        case = build_dma_vector(cfg, subsystem=compute, destination=target,
                                count=count, length=nbytes, profile="dma_only")
        head = case.manifest["descriptor_head"]
        trace_phase(f'{compute} stage={stage}: CPU0 AXI BFM populates DMA-only SRAM over real NoCs')
        await prep_sram(cpu0_data_bfm, case)
        csr = csr_by_name[compute+".dma"]
        # Two 32-bit writes to shared SRAM-staged 64-bit descriptor pointer.
        # The following doorbell atomically commits that pointer to upstream
        # 64-bit iDMA APB. For SS1 these writes cross global config FlooNoC.
        await write_word(cpu0_config_bfm, csr+0, head & 0xffffffff)
        await write_word(cpu0_config_bfm, csr+4, head >> 32)
        assert await read_word(cpu0_config_bfm, csr+0) == (head & 0xffffffff)
        trace_phase(f'{compute}: submit native iDMA head through 32-bit CSR NoC')
        await write_word(cpu0_config_bfm, csr+8, 1)
        # Testbench observes sticky IRQ; CPUs do not spin/poll descriptors.
        for _ in range(60000):
            if int(dut.dma_irq_pending_o.value) & (1 << i):
                break
            await RisingEdge(dut.clk_i)
        else:
            summarize_accepted_axi(dut, compute)
            try:
                status = await read_word(cpu0_config_bfm, csr+12)
                dut._log.error("DMA timeout STATUS %s CSR=%#x value=%#x", compute, csr, status)
            except Exception as exc:
                dut._log.error("DMA timeout CSR status unavailable: %s", exc)
            raise AssertionError(f"DMA IRQ timeout in {compute} -> {target}, "
                                 f"{count} descriptors at stage {stage}")
        status = await read_word(cpu0_config_bfm, csr+12)
        assert status & 2, f"DMA completion bit absent in {compute}: {status:#x}"
        assert not status & 4, f"DMA APB submission error in {compute}: {status:#x}"
        trace_phase(f'{compute}: verify real DMA destination + completion writebacks')
        for entry in case.manifest["copies"]:
            # Every payload byte is read back over the same real NoC graph,
            # not an internal SRAM memory handle or a mock DMA scoreboard.
            rd = await bounded(cpu0_data_bfm.read(entry["dst"], entry["length"]),
                               f"readback {target}")
            await check_ok(rd, "DMA target readback")
            assert bytes(rd.data) == bytes.fromhex(entry["expected_hex"]), (
                f"{compute} descriptor {entry['descriptor']:#x} corrupted {target}")
            wb = await bounded(cpu0_data_bfm.read(entry["descriptor"], 8),
                               "descriptor writeback")
            await check_ok(wb, "descriptor writeback")
            assert wb.data == b"\xff"*8, (
                f"{compute} descriptor completion writeback missing")
        await write_word(cpu0_config_bfm, csr+8, 2)
        for _ in range(300):
            if not (int(dut.dma_irq_pending_o.value) & (1 << i)):
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError(f"IRQ acknowledge did not clear for {compute}")
        dut._log.info("PASS chipdma: %s %d real descriptors -> %s over full NoC",
                      compute, count, target)
    dut._log.info("PASS chipdma: both compute DMA engines, 105 real transfers, "
                  "local/global data and configuration FlooNoCs, DDR/HBM")
