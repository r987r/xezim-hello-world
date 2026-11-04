"""Memory-subsystem-only preflight tests; no simulator or shared SoC writes."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bringup
import sim_model


class TestDDR4Contract(unittest.TestCase):
    def setUp(self):
        self.soc = {
            "buses": {"data": {"protocol": "axi4", "addr_bits": 64,
                               "data_bits": 64, "id_bits": 4}},
            "memory_targets": [{
                "name": "memory0.ddr0", "kind": "ddr", "controller": "litedram",
                "simulation": {"backend": "axi_ram"},
            }],
            "address_map": {"data": [{
                "name": "memory0.ddr0", "base": "0x140000000", "size": "0x40000000",
            }]},
            "networks": {"global_data": {"outputs": [
                {"name": "memory_ingress1", "target": "memory0.ddr0"}
            ]}},
        }
        self.lock = {"third_party": {"litedram": {
            "git": "https://github.com/enjoy-digital/litedram.git",
            "commit": "3506dc02e2b790011c1c147e2aad4541a6ddf836",
            "license": "BSD-2-Clause",
        }}}
        self.profile = bringup.read_yaml(bringup.PROFILE)
        self.noc = {"slaves": [{
            "endpoint": "target_crossbar", "addr_width": 64,
            "data_width": 64, "id_width": 4,
        }]}

    def check(self):
        return bringup.validate(self.soc, self.lock, self.profile,
                                "memory0.ddr0", self.noc)

    def test_current_contract(self):
        contract = self.check()
        self.assertEqual(contract["base"], 0x140000000)
        self.assertEqual(contract["size"], 0x40000000)
        self.assertEqual(contract["axi_id_bits"], 4)

    def test_bad_axi_data_width_rejected(self):
        self.soc["buses"]["data"]["data_bits"] = 128
        with self.assertRaisesRegex(ValueError, "data_bits"):
            self.check()

    def test_bad_axi_id_width_rejected(self):
        self.profile["user_ports"]["axi_0"]["id_width"] = 5
        with self.assertRaisesRegex(ValueError, "AXI ID width"):
            self.check()

    def test_missing_global_route_rejected(self):
        self.soc["networks"]["global_data"]["outputs"] = []
        with self.assertRaisesRegex(ValueError, "not reachable"):
            self.check()

    def test_window_must_be_aligned(self):
        self.soc["address_map"]["data"][0]["base"] = "0x140000001"
        with self.assertRaisesRegex(ValueError, "aligned"):
            self.check()

    def test_controller_init_not_bypassed(self):
        self.profile["user_ports"]["axi_0"]["block_until_ready"] = False
        with self.assertRaisesRegex(ValueError, "init"):
            self.check()

    def test_refresh_not_disabled(self):
        self.profile["with_refresh"] = False
        with self.assertRaisesRegex(ValueError, "refresh"):
            self.check()

    def test_noc_generated_width_mismatch(self):
        self.noc["slaves"][0]["id_width"] = 5
        with self.assertRaisesRegex(ValueError, "memory-local AXI id"):
            self.check()

    def test_unpinned_upstream_rejected(self):
        self.lock["third_party"]["litedram"]["commit"] = "main"
        with self.assertRaisesRegex(ValueError, "immutable commit"):
            self.check()


class TestDDR4GeneratedHeader(unittest.TestCase):
    @staticmethod
    def fixture() -> str:
        # Minimal ANSI header representing LiteDRAM standalone port naming.
        port_lines = []
        for short, width in bringup.AXI_SIGNALS.items():
            decl = f"[{width - 1}:0] " if width > 1 else ""
            port_lines.append(f"    input wire {decl}user_port_axi_0_{short}")
        port_lines += [
            "    input wire [31:0] user_port_axi_0_awaddr",
            "    input wire [31:0] user_port_axi_0_araddr",
            "    output wire init_done",
            "    input wire wb_ctrl_cyc",
        ]
        return "module soc_ddr4_sim (\n" + ",\n".join(port_lines) + "\n);\nendmodule\n"

    def test_expected_axi_ports_present(self):
        widths = bringup.emitted_port_widths(self.fixture())
        self.assertEqual(widths["user_port_axi_0_awaddr"], 32)
        self.assertEqual(widths["user_port_axi_0_wdata"], 64)
        self.assertEqual(widths["user_port_axi_0_rid"], 4)

    def test_missing_channel_rejected(self):
        text = self.fixture().replace("user_port_axi_0_rresp", "removed_rresp")
        with self.assertRaisesRegex(ValueError, "rresp"):
            bringup.emitted_port_widths(text)

    def test_wrong_strobe_width_rejected(self):
        text = self.fixture().replace("[7:0] user_port_axi_0_wstrb",
                                      "[3:0] user_port_axi_0_wstrb")
        with self.assertRaisesRegex(ValueError, "wstrb"):
            bringup.emitted_port_widths(text)

    def test_different_read_address_width_rejected(self):
        text = self.fixture().replace("[31:0] user_port_axi_0_araddr",
                                      "[29:0] user_port_axi_0_araddr")
        with self.assertRaisesRegex(ValueError, "different widths"):
            bringup.emitted_port_widths(text)

    def test_init_status_port_required(self):
        text = self.fixture().replace("init_done", "init_not_done")
        with self.assertRaisesRegex(ValueError, "init_done"):
            bringup.emitted_port_widths(text)



class TestDDR4SimGeometry(unittest.TestCase):
    def setUp(self):
        self.profile = bringup.read_yaml(bringup.PROFILE)
        self.geometry = bringup.read_yaml(bringup.HERE / "sim_geometry.yml")

    def test_scaled_geometry_bounded(self):
        info = sim_model.budget(self.profile, self.geometry)
        self.assertEqual(info["production_device_bytes"], 4 * 1024 ** 3)
        self.assertEqual(info["isolated_simulation_bytes"], 32 * 1024 ** 2)
        self.assertLessEqual(info["isolated_simulation_bytes"], info["max_model_bytes"])
        self.assertTrue(info["simulation_only"])

    def test_real_geometry_is_over_budget(self):
        self.geometry["simulation"]["rows"] = 32768
        self.geometry["simulation"]["cols"] = 1024
        with self.assertRaisesRegex(ValueError, "exceeds budget"):
            sim_model.budget(self.profile, self.geometry)

    def test_row_geometry_preserves_command_bit(self):
        self.geometry["simulation"]["rows"] = 1024
        with self.assertRaisesRegex(ValueError, "A10"):
            sim_model.budget(self.profile, self.geometry)

    def test_wrong_upstream_module_rejected(self):
        self.geometry["module"] = "NotAPinnedDevice"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            sim_model.budget(self.profile, self.geometry)

    def test_invalid_budget_fails(self):
        self.geometry["max_model_bytes"] = 0
        with self.assertRaisesRegex(ValueError, "positive"):
            sim_model.budget(self.profile, self.geometry)

    def test_sim_model_preserves_full_dfi_address_width(self):
        class Device:
            nbanks = 16
            nrows = 32768
            ncols = 1024

            def __init__(self):
                from types import SimpleNamespace
                self.geom_settings = SimpleNamespace(addressbits=self.nrows.bit_length()-1,
                                                     rowbits=self.nrows.bit_length()-1)

        scaled = sim_model.scaled_device_class(Device, self.geometry)
        instance = scaled()
        self.assertEqual(instance.geom_settings.rowbits, 11)
        self.assertEqual(instance.geom_settings.addressbits, 15)
        self.assertEqual(scaled.nrows, 2048)
        self.assertEqual(Device.nrows, 32768)

    def test_source_geometry_change_rejected(self):
        class Device:
            nbanks = 8
            nrows = 32768
            ncols = 1024

        with self.assertRaisesRegex(ValueError, "banks changed"):
            sim_model.scaled_device_class(Device, self.geometry)

    def test_generator_output_confined_to_ddr_sandbox(self):
        allowed = bringup.checked_output_dir(bringup.ROOT / ".tools/ddr4/test-output")
        self.assertEqual(allowed, (bringup.ROOT / ".tools/ddr4/test-output").resolve())
        for forbidden in (bringup.ROOT / "gen/chip", bringup.ROOT / "rtl/memory/ddr4",
                          bringup.ROOT / ".tools/litedram"):
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError, ".tools/ddr4"):
                    bringup.checked_output_dir(forbidden)

    def test_generator_uses_isolated_entrypoint(self):
        cmd = bringup.generator_argv(Path("/tmp/out"))
        self.assertEqual(Path(cmd[1]).name, "sim_model.py")
        self.assertIn("--sim", cmd)
        self.assertEqual(cmd[-1], str(bringup.PROFILE))

if __name__ == "__main__":
    unittest.main()
