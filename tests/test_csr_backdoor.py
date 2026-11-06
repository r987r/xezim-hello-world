"""CSR composition/RTL backdoor binding contract tests; no simulator claims."""
import unittest

from tools.csr_backdoor import BindingError, bind, compose


def catalog(instances=2):
    return {"schema_version": 1, "variant": "cpu_dma",
            "instances": [
                {"name": f"compute{i}.dma", "base": hex(0x40000000 + i * 0x10000),
                 "size": "0x10000", "status": "implemented",
                 "registers": [{
                     "name": "status", "offset": "0xc", "size_bytes": 4,
                     "fields": [
                         {"name": "irq_pending", "lsb": 1, "msb": 1,
                          "backdoor_policy": "backdoor_read_only"},
                         {"name": "busy", "lsb": 0, "msb": 0,
                          "backdoor_policy": "backdoor_read_only"},
                         {"name": "command", "lsb": 2, "msb": 2,
                          "backdoor_policy": "frontdoor_only"},
                     ]}]}
                for i in range(instances)
            ]}


def inventory(instances=2):
    return {"schema_version": 1, "variant": "cpu_dma", "simulator": "verilator",
            "top": "tb.dut", "build_sha256": "ab" * 32,
            "objects": [{"path": f"tb.dut.g_compute[{i}].status_q",
                         "kind": "logic", "width_bits": 32, "writable": True}
                        for i in range(instances)]}


class CsrBackdoorTests(unittest.TestCase):
    def test_repeated_instances_unique_addresses_and_storage(self):
        model = compose(catalog())
        self.assertEqual(len(model["fields"]), 6)
        self.assertEqual([x["address"] for x in model["fields"][::3]],
                         ["0x4000000c", "0x4001000c"])
        bindings = [
            {"logical_path": f"compute{i}.dma.status.{name}",
             "rtl_path": f"tb.dut.g_compute[{i}].status_q", "rtl_lsb": bit}
            for i in range(2) for name, bit in (("irq_pending", 1), ("busy", 0))
        ]
        result = bind(model, inventory(), bindings)
        self.assertEqual([x["status"] for x in result["fields"]].count("bound_unvalidated"), 4)
        self.assertEqual([x["status"] for x in result["fields"]].count("unavailable"), 2)
        self.assertEqual(result["qualification"],
                         "bindings_checked_against_elaboration_not_frontdoor_verified")

    def test_unknown_and_stale_hierarchy_fail_closed(self):
        model = compose(catalog())
        with self.assertRaisesRegex(BindingError, "absent from elaborated"):
            bind(model, inventory(), [{"logical_path": model["fields"][0]["logical_path"],
                                        "rtl_path": "tb.dut.missing"}])
        old = inventory()
        old["variant"] = "cold_boot"
        with self.assertRaisesRegex(BindingError, "variant differs"):
            bind(model, old, [])

    def test_side_effect_policy_blocks_raw_paths(self):
        model = compose(catalog(1))
        with self.assertRaisesRegex(BindingError, "policy prohibits"):
            bind(model, inventory(1), [{
                "logical_path": "compute0.dma.status.command",
                "rtl_path": "tb.dut.g_compute[0].status_q",
                "rtl_lsb": 2
            }])

    def test_duplicate_physical_bits_fail(self):
        model = compose(catalog(1))
        path = "tb.dut.g_compute[0].status_q"
        with self.assertRaisesRegex(BindingError, "aliased physical"):
            bind(model, inventory(1), [
                {"logical_path": "compute0.dma.status.irq_pending",
                 "rtl_path": path, "rtl_lsb": 0},
                {"logical_path": "compute0.dma.status.busy",
                 "rtl_path": path, "rtl_lsb": 0},
            ])

    def test_no_implicit_registers_in_reserved_aperture(self):
        item = catalog(1)
        item["instances"][0]["status"] = "unmapped_or_disabled"
        with self.assertRaisesRegex(BindingError, "unavailable instance"):
            compose(item)
        item["instances"][0]["registers"] = []
        self.assertEqual(compose(item)["fields"], [])

    def test_bounds_unknown_policy_and_missing_build(self):
        item = catalog(1)
        item["instances"][0]["registers"][0]["offset"] = "0x10000"
        with self.assertRaisesRegex(BindingError, "out of bounds"):
            compose(item)
        item = catalog(1)
        item["instances"][0]["registers"][0]["fields"][0]["backdoor_policy"] = "raw_anything"
        with self.assertRaisesRegex(BindingError, "unrecognized"):
            compose(item)
        inv = inventory(1)
        inv["build_sha256"] = ""
        with self.assertRaisesRegex(BindingError, "elaboration evidence"):
            bind(compose(catalog(1)), inv, [])


if __name__ == "__main__":
    unittest.main()
