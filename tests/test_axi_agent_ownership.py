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
    "dv/full_chip/test_dma.py": {
        "allowed": {"AxiMaster"},
        "reason": "DmaTestMode=1 holds CPUs reset; BFMs own CPU0 ports",
    },
    "dv/supernoc/test_supernoc.py": {
        "allowed": {"AxiMaster", "AxiSlave"},
        "reason": "No CPU/DMA; BFM masters own exposed NoC inputs, slaves own outputs",
    },
    "dv/dma/test_dma.py": {
        "allowed": {"AxiSlave"},
        "reason": "DMA RTL drives AXI output, host sparse memory owns slave response",
    },
    "rtl/memory/ddr4/functional_tb.py": {
        "allowed": {"AxiMaster"},
        "reason": "External AXI master accesses isolated real DDR controller",
    },
    "dv/pcie0/rtl_smoke.py": {
        "allowed": {"AxiRam"},
        "reason": "Isolated PCIe TLP-to-AXI RTL bridge is sole AXI4 manager; AxiRam alone owns the exposed m_axi target response. No live SoC CPU, DMA, SRAM, or NoC is attached in this test.",
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
                    and node.name == "coordinated_cold_boot")
        masters = [node for node in ast.walk(boot)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id == "AxiMaster"]
        self.assertEqual(len(masters), 1)
        guards = [node for node in ast.walk(boot)
                  if isinstance(node, ast.If)
                  and isinstance(node.test, ast.UnaryOp)
                  and isinstance(node.test.op, ast.Not)
                  and isinstance(node.test.operand, ast.Name)
                  and node.test.operand.id == "cpu_dma_mode"]
        self.assertEqual(len(guards), 1)
        self.assertIn(masters[0], list(ast.walk(guards[0])))
        self.assertIn("assert probe is None", src)
        gen = (ROOT/"tools/full_chip_gen.py").read_text()
        self.assertIn(".ProbeEnable(1'b0), .DmaEnable(1'b1)", gen)
        self.assertIn("DmaTestMode ? probe_req : cpu_data_", gen)
        self.assertIn("cpu_reset_n[{i}] = ({release}) && !DmaTestMode", gen)

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
