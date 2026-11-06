"""Ownership audit for AXI BFMs vs passive monitors and live RTL ports.

Agent = protocol participant (drives request/ready or response).
Monitor = observation only, never drives signals.
The real-CPU DMA variant MUST NOT attach an AxiMaster to mirrored iDMA
response wires; it caused cocotbext-axi 'unexpected burst ID' on ID 7.
Review every new testbench entry here rather than globally disabling BFMs.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

# Every cocotb testbench currently constructing an active AXI agent must be
# explicitly classified by which RTL side is held/absent or externally exposed.
AGENT_SCOPES = {
    "dv/full_chip/test_boot.py": {
        "allowed": {"AxiMaster"},
        "reason": "BFM only in default boot; real CPU+DMA forbids it",
    },
    "dv/full_chip/test_ddr_real.py": {
        "allowed": {"AxiMaster"},
        "reason": "Opt-in real DDR only; after CPU/iDMA CHECK and drained controller requests, a verification AXI master exclusively owns compute0 DMA manager port for routed DECERR/nonalias tests",
    },
    "dv/full_chip/ddr_init.py": {
        "allowed": {"AxiMaster"},
        "reason": "CPU0 is held by real DDR DdrInitMode; BFM owns only Config NoC preboot initialization and is disconnected before CPU release",
    },
    "dv/full_chip/test_dma.py": {
        "allowed": {"AxiMaster"},
        "reason": "DmaTestMode=1 holds CPUs reset; BFMs own CPU0 ports",
    },
    "dv/ethernet0/test_chip_mvp.py": {
        "allowed": {"AxiMaster"},
        "reason": "Ethernet opt-in chip uses DmaTestMode=1, which holds both CPUs in reset; the two BFMs exclusively own CPU0 Data and Config NoC ports while physical GMII MAC/AXI DMA run autonomously",
    },
    "dv/supernoc/test_supernoc.py": {
        "allowed": {"AxiMaster", "AxiSlave"},
        "reason": "No CPU/DMA; BFM masters own exposed NoC inputs, slaves own outputs",
    },
    "dv/dma/test_dma.py": {
        "allowed": {"AxiSlave"},
        "reason": "DMA RTL drives AXI output, host sparse memory owns slave response",
    },
    "dv/pcie0/rtl_smoke.py": {
        "allowed": {"AxiRam"},
        "reason": "Isolated PCIe TLP-to-AXI bridge has no CPU or NoC; upstream AxiRam is the sole memory responder",
    },
    "rtl/memory/ddr4/functional_tb.py": {
        "allowed": {"AxiMaster"},
        "reason": "External AXI master accesses isolated real DDR controller",
    },
}


def calls(source):
    tree = ast.parse(source)
    return [(node, node.func.id) for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"AxiMaster", "AxiSlave", "AxiRam"}]


class AgentOwnershipTests(unittest.TestCase):
    def test_all_active_agents_have_explicit_reviewed_ownership(self):
        testbenches = list((ROOT/"dv").rglob("*.py"))
        testbenches += list((ROOT/"rtl/memory").rglob("*.py"))
        discovered = {}
        for path in testbenches:
            rel = path.relative_to(ROOT).as_posix()
            found = {name for _, name in calls(path.read_text())}
            if found:
                discovered[rel] = found
                self.assertIn(rel, AGENT_SCOPES,
                              f"Active AXI participant in {rel} needs ownership review")
                self.assertEqual(found, AGENT_SCOPES[rel]["allowed"])
        self.assertEqual(set(discovered), set(AGENT_SCOPES))

    def test_cpu_and_dma_are_mutually_exclusive_with_probe_bfm(self):
        src = (ROOT/"dv/full_chip/test_boot.py").read_text()
        tree = ast.parse(src)
        boot = next(node for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "execute_cold_boot")
        masters = [node for node in ast.walk(boot)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id == "AxiMaster"]
        self.assertEqual(len(masters), 1)
        guards = [node for node in ast.walk(boot)
                  if isinstance(node, ast.If)
                  and isinstance(node.test, ast.BoolOp)
                  and isinstance(node.test.op, ast.And)
                  and ast.unparse(node.test) == "not cpu_dma_mode and host is None"]
        self.assertEqual(len(guards), 1)
        self.assertIn(masters[0], list(ast.walk(guards[0])))
        self.assertIn("assert probe is None", src)
        gen = (ROOT/"tools/full_chip_gen.py").read_text()
        self.assertIn(".ProbeEnable(1'b0), .DmaEnable(1'b1)", gen)
        self.assertIn("DmaTestMode ? probe_req : cpu_data_", gen)
        self.assertIn("cpu_reset_n[{i}] = ({release}) && !DmaTestMode", gen)

    def test_ddr_negative_routed_probe_after_cpu_check(self):
        gen = (ROOT / "tools/full_chip_gen.py").read_text()
        check = (ROOT / "dv/full_chip/test_ddr_real.py").read_text()
        self.assertIn("ddr_negative_mode_i ? probe_req", gen)
        self.assertIn("dma_engine_rsp = f'dma_{i}_hw_rsp'", gen)
        self.assertIn("ddr_negative_mode && (!pass_flag || ddr_init_mode)", gen)
        self.assertIn("await execute_cold_boot(dut)", check)
        self.assertIn("dut.ddr_negative_mode.value = 1", check)
        self.assertIn('expect_axi_response("compute0_local_data.dma"', check)
        self.assertIn("AxiResp.DECERR", check)
        self.assertIn("counts_before == counts_after", check)
        self.assertIn("after.data == pattern", check)

    def test_ddr_config_bfm_cannot_contend_with_cpu(self):
        driver = (ROOT/"dv/full_chip/ddr_init.py").read_text()
        boot = (ROOT/"dv/full_chip/test_boot.py").read_text()
        gen = (ROOT/"tools/full_chip_gen.py").read_text()
        self.assertIn('cfg = AxiMaster(AxiBus.from_prefix(dut, "cfgprobe")', driver)
        self.assertIn("assert int(dut.ddr_init_mode.value) == 1", driver)
        self.assertIn("dut.ddr_init_mode.value = 0", driver)
        self.assertIn("dut.ddr_init_mode.value = 1", boot)
        self.assertIn("await initialize_controller(dut)", boot)
        self.assertIn("release += ' && !ddr_init_mode_i'", gen)
        self.assertIn("ddr_init_mode_i ? cfgprobe_req", gen)
        self.assertIn("ddr_init_mode_i ? {field(rsp(cfg_port),ch,member)} : '0;", gen)
        self.assertNotIn("probe = AxiMaster", driver)

    def test_cpu0_bfm_only_when_real_cpu_held_reset(self):
        src = (ROOT/"dv/full_chip/test_dma.py").read_text()
        self.assertIn("cpu0_data_bfm = AxiMaster", src)
        self.assertIn("cpu0_config_bfm = AxiMaster", src)
        gen = (ROOT/"tools/full_chip_gen.py").read_text()
        self.assertIn("(.ProbeEnable(1'b1), .DmaEnable(1'b1), .DmaTestMode(1'b1))", gen)
        self.assertIn("CPU0 AXI BFM mode requires active DMA and probe", gen)

    def test_passive_axi_trace_never_drives_a_bus(self):
        src = (ROOT/"dv/common/axi_trace.py").read_text()
        tree = ast.parse(src)
        self.assertFalse(calls(src))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            # No signal .value write: only software bookkeeping is allowed.
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == "value":
                    self.fail("Passive AXI observer unexpectedly writes an RTL signal")
        self.assertIn("Monitor", src)
        self.assertIn("await monitor.recv()", src)

    def test_supernoc_and_ddr_external_ports_are_intentional(self):
        noc = (ROOT/"dv/supernoc/test_supernoc.py").read_text()
        self.assertIn('for entry in CONTRACT["masters"]:', noc)
        self.assertIn('for entry in CONTRACT["slaves"]:', noc)
        self.assertIn('AxiBus.from_prefix(dut, name)', noc)
        ddr = (ROOT/"rtl/memory/ddr4/functional_tb.py").read_text()
        self.assertIn('AxiBus.from_prefix(dut, "user_port_axi_0")', ddr)
        isolated = (ROOT/"dv/dma/test_dma.py").read_text()
        self.assertIn("SparseMemoryRegion", isolated)
        self.assertIn("AxiSlave(", isolated)

    def test_sv_memory_bfm_and_route_monitor_ownership(self):
        # The standalone memory fabric uses its own SV AXI master BFM,
        # never the executing SoC CPUs or their DMA port.
        generator = (ROOT/"tools/socgen.py").read_text()
        memory_tb = (ROOT/"gen/memory/memory_tb.sv").read_text()
        active = (ROOT/"dv/common/axi_master_bfm.sv").read_text()
        passive = (ROOT/"dv/common/axi_route_monitor.sv").read_text()
        self.assertIn("axi_master_bfm #(", generator)
        self.assertIn("axi_master_bfm #(", memory_tb)
        self.assertIn("module axi_master_bfm", active)
        self.assertIn("output reg", active)
        self.assertIn("module axi_route_monitor", passive)
        # Port declarations on the passive monitor must remain input-only.
        ports = passive.split(");", 1)[0]
        self.assertNotIn("output wire", ports)
        self.assertNotIn("output reg", ports)
        self.assertIn("m_awvalid[target] && m_awready[target]", passive)
        self.assertIn("m_arvalid[target] && m_arready[target]", passive)
        chip_gen = (ROOT/"tools/full_chip_gen.py").read_text()
        self.assertNotIn("axi_master_bfm #(", chip_gen)

    def test_ddr_observer_is_read_only_and_init_is_external(self):
        observer = (ROOT/"rtl/memory/ddr4/traffic_observer.py").read_text()
        tree = ast.parse(observer)
        for node in ast.walk(tree):
            # Only reads of simulator DUT pins: no .value assignments.
            targets = ([*node.targets] if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign))
                       else [])
            self.assertFalse(any(isinstance(t, ast.Attribute) and t.attr=="value"
                                 for t in targets),
                             "DDR passive observer must not drive DUT pins")
        bench = (ROOT/"rtl/memory/ddr4/functional_tb.py").read_text()
        self.assertIn('AxiBus.from_prefix(dut, "user_port_axi_0")', bench)
        self.assertIn("TrafficObserver", bench)
        self.assertIn("await initialize(dut)", bench)
