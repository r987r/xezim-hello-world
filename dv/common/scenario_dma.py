"""SCN-2 adapter for a *single* source-neutral real-iDMA DDR roundtrip.

The compiler creates immutable C constants from the SAME validated scenario
plan consumed by the reset-isolated cocotb AXI drivers. No software-only
execution or simulated bus response is counted as hardware evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dv.common.scenario import ScenarioError, canonical_json, resolve_scenario

EXAMPLE = Path("config/scenarios/cpu-bfm-ddr-roundtrip.json")
REQUIRED = {
    "alloc_source": "memory.allocate",
    "alloc_ddr": "memory.allocate",
    "alloc_return": "memory.allocate",
    "init_source": "memory.initialize",
    "copy_out": "dma.copy",
    "copy_back": "dma.copy",
    "wait_idle": "dma.wait_idle",
    "check_return": "memory.check",
}


def compile_contract(plan: dict) -> dict:
    """Fail closed if a generic scenario cannot be executed by THIS adapter."""
    if (type(plan) is not dict or plan.get("kind") != "soc_scenario_intent_only"
            or plan.get("execution_evidence") is not None
            or plan.get("schema_version") != 1
            or plan.get("variant") != "boot_live"):
        raise ScenarioError("SCN-2 requires verified v1 boot_live *intent*, not execution evidence")
    actions = {a["action_instance_id"]: a for a in plan["actions"]}
    if len(actions) != len(plan["actions"]) or set(actions) != set(REQUIRED):
        raise ScenarioError("SCN-2 adapter supports exactly the 8-action DDR roundtrip")
    for aid, kind in REQUIRED.items():
        if actions[aid]["kind"] != kind:
            raise ScenarioError(f"{aid}: incompatible action kind")
    allocations = {b["buffer"]: b for b in plan["allocations"]}
    if set(allocations) != {"src", "ddr", "return"}:
        raise ScenarioError("SCN-2 needs only src, DDR and return buffers")
    src, ddr, ret = allocations["src"], allocations["ddr"], allocations["return"]
    if (src["region"] != "compute0.sram.payload"
            or ret["region"] != src["region"]
            or ddr["region"] != "memory0.ddr0"):
        raise ScenarioError("SCN-2 needs CPU0 payload and modeled DDR")
    nbytes = actions["copy_out"]["args"]["length"]
    init = actions["init_source"]["args"]
    check = actions["check_return"]["args"]
    if (type(nbytes) is not int or not 1 <= nbytes <= 256
            or nbytes % 8 or src["size"] != nbytes
            or ret["size"] != nbytes or ddr["size"] != nbytes
            or any(b["phys"] % 64 for b in (src, ddr, ret))
            or actions["alloc_source"]["actor"] != "cpu0"
            or actions["alloc_return"]["actor"] != "cpu0"
            or actions["alloc_ddr"]["actor"] != "cpu0"):
        raise ScenarioError("SCN-2 unsupported allocation/length/ownership")
    if (init != {"buffer": "src", "length": nbytes,
                 "pattern": {"kind": "constant", "seed": init["pattern"]["seed"]},
                 "policy": "strict"}
            or check != {"buffer": "return", "length": nbytes,
                         "pattern": init["pattern"], "policy": "strict",
                         "expected_from": "src"}):
        raise ScenarioError("SCN-2 supports a matched constant source-origin golden recipe")
    if actions["copy_out"]["args"] != {"engine": "compute0.dma",
                                       "src": "src", "dst": "ddr", "length": nbytes}:
        raise ScenarioError("SCN-2 source -> DDR copy does not match plan")
    if actions["copy_back"]["args"] != {"engine": "compute0.dma",
                                        "src": "ddr", "dst": "return", "length": nbytes}:
        raise ScenarioError("SCN-2 DDR -> return copy does not match plan")
    if (actions["wait_idle"]["args"] != {"engine": "compute0.dma"}
            or actions["wait_idle"]["phase"] != "run"
            or actions["check_return"]["phase"] != "check"
            or init["pattern"]["seed"] > 0xffffffff):
        raise ScenarioError("SCN-2 check/idle/seed unsupported")
    for aid in ("copy_out", "copy_back"):
        if actions[aid]["phase"] != "run":
            raise ScenarioError(f"{aid} must execute in RUN")
    # Semantic control and data dependencies are part of the executor ABI.
    deps = {aid: set(a["depends_on"]) for aid, a in actions.items()}
    required_deps = {"alloc_return": {"alloc_source"},
                     "init_source": {"alloc_source"},
                     "copy_out": {"init_source", "alloc_ddr"},
                     "copy_back": {"copy_out", "alloc_return"},
                     "wait_idle": {"copy_back"},
                     "check_return": {"wait_idle", "init_source"}}
    if any(deps[aid] != needed for aid, needed in required_deps.items()):
        raise ScenarioError("SCN-2 dependency contract differs from executor ordering")
    return {
        "scenario_id": plan["scenario_id"],
        "plan_sha256": hashlib.sha256(canonical_json(plan).encode("ascii")).hexdigest(),
        "length": nbytes,
        "seed": init["pattern"]["seed"],
        "source_phys": src["phys"],
        "ddr_phys": ddr["phys"],
        "return_phys": ret["phys"],
        "source_region_base": next(r["base"] for r in plan["regions"]
                                   if r["name"] == "compute0.sram.payload"),
        "ddr_region_base": next(r["base"] for r in plan["regions"]
                                if r["name"] == "memory0.ddr0"),
        "engine": "compute0.dma",
        "execution_state": "pending_real_rtl",
    }


def render_c_header(contract: dict) -> str:
    """Generate no C bus driver: constants for existing freestanding DMA code."""
    names = {
        "SOC_SCN_LENGTH": contract["length"],
        "SOC_SCN_SEED": contract["seed"],
        "SOC_SCN_SOURCE_PHYS": contract["source_phys"],
        "SOC_SCN_DDR_PHYS": contract["ddr_phys"],
        "SOC_SCN_RETURN_PHYS": contract["return_phys"],
        "SOC_SCN_SRC_POOL_PHYS": contract["source_region_base"],
        "SOC_SCN_DDR_POOL_PHYS": contract["ddr_region_base"],
    }
    return ("/* Generated from canonical scenario-plan.json; never hand edit. */\n"
            "#ifndef SOC_SCENARIO_DMA_CONTRACT_H\n#define SOC_SCENARIO_DMA_CONTRACT_H\n"
            + "".join(f"#define {key} 0x{value:x}ULL\n" for key, value in names.items())
            + "#endif\n")


def materialize(cfg: dict, out: Path, *, source_revision: str | None = None,
                scenario_seed: int | None = None) -> tuple[dict, dict]:
    from dv.common.scenario import canonical_json
    import yaml
    # Resolve from checked-in source once; both execution profiles use the
    # same bytes, with the same optional source SHA, not separate generators.
    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / EXAMPLE).read_text())
    if scenario_seed is not None:
        if type(scenario_seed) is not int or not 0 <= scenario_seed <= 0xffffffff:
            raise ScenarioError('SCN-2 scenario override must be uint32')
        spec['seed'] = scenario_seed
    plan = resolve_scenario(spec, cfg, source_revision=source_revision)
    contract = compile_contract(plan)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scenario-plan.json").write_text(canonical_json(plan), encoding="ascii")
    (out / "scenario_dma_contract.h").write_text(render_c_header(contract))
    (out / "scenario-contract.json").write_text(canonical_json(contract))
    return plan, contract


def load_contract_from_plan(path: Path) -> dict:
    """Reject modified/stale resolved plans before issuing ANY AXI transaction."""
    plan = json.loads(path.read_text())
    return compile_contract(plan)


async def execute_bfm_roundtrip(dut, data_master, csr_master, contract: dict,
                                *, wait_cycles: int = 60000) -> None:
    """Dispatch the exact typed SCN-1 plan through genuine RTL iDMA and AXI BFMs.

    This records *driver-only* action stages. The caller still requires
    independent accepted AXI captures and byte checks for its RTL PASS.
    """
    import os
    from cocotb.triggers import RisingEdge, with_timeout
    from dv.common.dma_vectors import DESC, DESC_END, FLAGS_COPY, FLAGS_IRQ
    from dv.common.axi_trace import trace_phase
    from dv.common.action_runtime import ActionDispatcher, HandlerSpec
    from dv.common.action_events import ActionEventRecorder
    from tools.sram_layout import build_sram_layout
    from dv.common.scenario import canonical_json
    import yaml

    selected_path = os.environ.get("SOC_SCENARIO_PLAN")
    if not selected_path:
        raise ScenarioError("BFM scenario requires the selected source plan")
    raw = Path(selected_path).read_bytes()
    selected_plan = json.loads(raw)
    if canonical_json(selected_plan).encode("ascii") != raw:
        raise ScenarioError("BFM scenario plan has noncanonical source bytes")
    if compile_contract(selected_plan) != contract:
        raise ScenarioError("BFM driver contract differs from selected scenario")
    root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "config/soc.yaml").read_text())
    layout = build_sram_layout(cfg, "compute0", profile="boot_live")
    csr_base = next(int(r["base"], 0) for r in cfg["address_map"]["config"]
                    if r["name"] == contract["engine"])
    source = contract["source_phys"]
    target = contract["ddr_phys"]
    returned = contract["return_phys"]
    n = contract["length"]
    seed = contract["seed"]
    desc_phys = layout.descriptors.start
    if source < layout.payload.start or returned + n > layout.payload.end:
        raise AssertionError("SCN-2 BFM refused invalid SRAM plan")

    async def write(master, phys, payload: bytes, label: str):
        response = await with_timeout(master.write(phys, payload), 250, "us")
        if response.resp != 0:
            raise AssertionError(f"{label} AXI write response {response.resp}")

    async def read(master, phys, length: int, label: str) -> bytes:
        response = await with_timeout(master.read(phys, length), 250, "us")
        if response.resp != 0:
            raise AssertionError(f"{label} AXI read response {response.resp}")
        return bytes(response.data)

    async def command(word: int, value: int):
        await write(csr_master, csr_base + word,
                    value.to_bytes(4, "little"), "DMA CSR")

    async def run_one(src: int, dst: int, suffix: str):
        descriptor = DESC.pack(n, FLAGS_COPY | FLAGS_IRQ, DESC_END, src, dst)
        trace_phase(f"SCN-2 {suffix}: descriptor source and CSR via authorized BFM")
        await write(data_master, desc_phys, descriptor, "DMA descriptor")
        await command(0, desc_phys & 0xffffffff)
        await command(4, desc_phys >> 32)
        await command(8, 1)
        for _ in range(wait_cycles):
            if int(dut.dma_irq_pending_o.value) & 1:
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError(f"SCN-2 {suffix}: real DMA IRQ timeout")
        status = int.from_bytes(await read(csr_master, csr_base + 12, 4, "DMA status"), "little")
        if not status & 2 or status & 4:
            raise AssertionError(f"SCN-2 {suffix}: bad DMA status {status:#x}")
        writeback = await read(data_master, desc_phys, 8, "DMA descriptor writeback")
        if writeback != b"\xff" * 8:
            raise AssertionError(f"SCN-2 {suffix}: missing descriptor completion")
        await command(8, 2)
        for _ in range(300):
            if not (int(dut.dma_irq_pending_o.value) & 1):
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError("SCN-2 IRQ ACK did not clear")
        # Descriptor writeback and IRQ do NOT replace passive AXI correlation.

    # The selected allocations specify BFM-backed model addresses, not a CPU
    # memory-allocation or hardware mailbox operation. Strictly verify the
    # addresses/region before dispatch, with no fabricated allocations.
    allocations = {item["buffer"]: item for item in selected_plan["allocations"]}
    memory = {"src": source, "ddr": target, "return": returned}
    pattern = bytes([seed & 0xff]) * n
    state = {"copied": [], "initialized": False, "checked": False}

    async def reserve(action, _):
        info = allocations[action["args"]["buffer"]]
        buf = action["args"]["buffer"]
        if (info["phys"] != memory[buf] or info["size"] != n or
                info["region"] != action["args"]["region"]):
            raise AssertionError(f"SCN-2 selected BFM reservation mismatch: {buf}")

    async def initialize(action, _):
        args = action["args"]
        if (args["buffer"] != "src" or args["length"] != n or
                args["pattern"]["seed"] != seed or
                args["pattern"]["kind"] != "constant"):
            raise AssertionError("SCN-2 unsupported source initialization")
        await write(data_master, source, pattern, "source SRAM")
        state["initialized"] = True

    async def copy(action, _):
        args = action["args"]
        src, dst = args["src"], args["dst"]
        if (args["engine"] != contract["engine"] or args["length"] != n
                or not state["initialized"]):
            raise AssertionError("SCN-2 unselected DMA action parameters")
        await run_one(memory[src], memory[dst], action["action_instance_id"])
        # Read through actual NoC AXI, never inspect a private memory object.
        actual = await read(data_master, memory[dst], n, f"{dst} readback")
        if actual != pattern:
            raise AssertionError(f"SCN-2 {dst} expected-vs-observed byte mismatch")
        state["copied"].append(action["action_instance_id"])

    async def wait_idle(action, _):
        if (action["args"]["engine"] != contract["engine"]
                or state["copied"] != ["copy_out", "copy_back"]):
            raise AssertionError("SCN-2 DMA wait did not follow actual transfers")
        status = int.from_bytes(await read(csr_master, csr_base + 12, 4, "DMA idle"), "little")
        if status & 4:
            raise AssertionError("SCN-2 real DMA reports APB error")

    async def check(action, _):
        args = action["args"]
        if (args["buffer"] != "return" or args["expected_from"] != "src"
                or args["length"] != n):
            raise AssertionError("SCN-2 unexpected independent readback recipe")
        actual = await read(data_master, returned, n, "SRAM return readback")
        if actual != pattern:
            raise AssertionError("SCN-2 SRAM return expected-vs-observed byte mismatch")
        state["checked"] = True

    # One source-selected capability registry for the existing real AXI
    # BFM, not another address/sequence planner. Explicit actor ownership
    # prevents a future mixed C/Python/SV plan dispatching CPU-only actions
    # through the DMA adapter (or vice versa). max_inflight=1 intentionally
    # preserves proven SCN-2 hardware traffic and original CI evidence.
    handlers = {
        "memory.allocate": HandlerSpec(reserve, actors=frozenset({"cpu0"})),
        "memory.initialize": HandlerSpec(initialize, actors=frozenset({"cpu0"})),
        "dma.copy": HandlerSpec(copy, actors=frozenset({"dma0"})),
        "dma.wait_idle": HandlerSpec(wait_idle, actors=frozenset({"cpu0"})),
        "memory.check": HandlerSpec(check, actors=frozenset({"checker0"})),
    }
    # Clock and simulated command output are original-run evidence only.
    # If no canonical run context exists, permit direct bench use without a
    # transcript; never create a misleading replacement report.
    run_plan = os.environ.get("SOC_RUN_PLAN")
    recorder = None
    if run_plan:
        from cocotb.utils import get_sim_time
        recorder = ActionEventRecorder(
            raw, Path(run_plan).parent / "action-events.jsonl",
            lambda: int(get_sim_time(units="ps")))
    try:
        dispatcher = ActionDispatcher(raw, handlers, recorder=recorder,
                                      expected_sha=contract["plan_sha256"])
        await dispatcher.run()
        if not state["checked"] or len(dispatcher.completed) != len(selected_plan["actions"]):
            raise AssertionError("SCN-2 typed action execution incomplete")
    except BaseException:
        # Retain the original real RTL/BFM error. A strict close() correctly
        # rejects unfinished actions, but must not mask the underlying cause.
        # Incomplete driver events stay in the original failed-run artifact.
        if recorder is not None and not recorder.closed:
            recorder.file.close()
            recorder.closed = True
        raise
    else:
        if recorder is not None:
            recorder.close()
    trace_phase(f"SCN-2 BFM typed real RTL DMA plan executed; scenario={contract['scenario_id']}")
