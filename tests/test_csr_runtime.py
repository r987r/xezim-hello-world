"""Runtime CSR hierarchy access: negative tests are mandatory."""
import unittest

from tools.csr_backdoor import BindingError, compose
from tools.csr_runtime import SafeCsrBackdoor, discover, resolve_handle


class Signal:
    def __init__(self, value, width=32):
        self.value = value
        self.width = width

    def __len__(self):
        return self.width


class Dut:
    _name = "top"

    def __init__(self):
        self.block = type("Block", (), {})()
        self.block.irq_q = Signal(0b1010, 32)


def model():
    return compose({
        "schema_version": 1, "variant": "cpu_dma",
        "instances": [{
            "name": "compute0.dma", "status": "implemented",
            "base": "0x40000000", "size": "0x100",
            "registers": [{
                "name": "status", "offset": "0xc", "size_bytes": 4,
                "fields": [
                    {"name": "irq_pending", "lsb": 1, "msb": 1,
                     "backdoor_policy": "backdoor_read_only"},
                    {"name": "busy", "lsb": 0, "msb": 0,
                     "backdoor_policy": "backdoor_read_only"},
                    {"name": "write_one_clear", "lsb": 2, "msb": 2,
                     "backdoor_policy": "frontdoor_only"}
                ]
            }]
        }]
    })


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.dut = Dut()
        self.composed = model()
        self.good = [{"logical_path": "compute0.dma.status.irq_pending",
                      "rtl_path": "top.block.irq_q", "rtl_lsb": 1},
                     {"logical_path": "compute0.dma.status.busy",
                      "rtl_path": "top.block.irq_q", "rtl_lsb": 0}]

    def adapter(self, specs=None, dut=None, **kwargs):
        return SafeCsrBackdoor(
            self.composed, dut or self.dut, build_sha256="ab"*32,
            simulator="verilator-cocotb",
            specs=self.good if specs is None else specs, **kwargs)

    def test_runtime_bound_read_only_field(self):
        adapter = self.adapter()
        self.assertEqual(adapter.read("compute0.dma.status.irq_pending"), 1)
        self.assertEqual(adapter.read("compute0.dma.status.busy"), 0)
        self.dut.block.irq_q.value = 0b0001
        self.assertEqual(adapter.read("compute0.dma.status.irq_pending"), 0)
        self.assertEqual(adapter.read("compute0.dma.status.busy"), 1)
        self.assertEqual(adapter.report["qualification"],
                         "bindings_checked_against_elaboration_not_frontdoor_verified")
        self.assertFalse(any(e.get("writable") for e in adapter.report["fields"]))

    def test_write_never_deposits_raw_hdl_values(self):
        adapter = self.adapter()
        with self.assertRaisesRegex(BindingError, "disabled"):
            adapter.write("compute0.dma.status.irq_pending", 0)
        self.assertEqual(self.dut.block.irq_q.value, 0b1010)

    def test_frontdoor_only_read_fails_closed(self):
        adapter = self.adapter()
        with self.assertRaisesRegex(BindingError, "policy prohibits"):
            adapter.read("compute0.dma.status.write_one_clear")
        with self.assertRaisesRegex(BindingError, "unknown"):
            adapter.read("compute0.dma.unknown")

    def test_missing_handle_marks_unavailable_and_strict_rejects(self):
        absent = [{"logical_path": "compute0.dma.status.irq_pending",
                   "rtl_path": "top.block.missing"}]
        adapter = self.adapter(specs=absent)
        with self.assertRaisesRegex(BindingError, "no qualified"):
            adapter.read("compute0.dma.status.irq_pending")
        with self.assertRaisesRegex(BindingError, "not available"):
            self.adapter(specs=absent, strict=True)

    def test_wrong_simulator_top_build_and_alias_fail(self):
        with self.assertRaisesRegex(BindingError, "actual simulator top"):
            resolve_handle(self.dut, "wrong.block.irq_q")
        with self.assertRaisesRegex(BindingError, "fingerprint"):
            discover(self.dut, variant="cpu_dma", build_sha256="fake",
                     simulator="verilator-cocotb", requested_paths=[])
        aliased = [
            {"logical_path": "compute0.dma.status.irq_pending",
             "rtl_path": "top.block.irq_q", "rtl_lsb": 0},
            {"logical_path": "compute0.dma.status.busy",
             "rtl_path": "top.block.irq_q", "rtl_lsb": 0},
        ]
        with self.assertRaisesRegex(BindingError, "aliased"):
            self.adapter(specs=aliased)


if __name__ == "__main__":
    unittest.main()
