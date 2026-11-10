"""Source-owned reset/ACK CSR field ABI regression against real SystemRDL.

These are generator/source checks, not proof of CPU MMIO or simulator access.
The separate PeakRDL full-chip test owns real Config-NoC qualification.
"""
from pathlib import Path
import tempfile
import unittest

from tools.csrgen import CsrError, compile_rdl, header, register_layout

ROOT = Path(__file__).resolve().parents[1]
RDL = ROOT / "csr/rdl/boot_reset_ctrl.rdl"


class ResetCsrAbiTests(unittest.TestCase):
    def test_core_count_changes_field_width_but_preserves_software_register_abi(self):
        for peers in (1, 2, 7, 15):
            with self.subTest(peers=peers):
                regs = register_layout(compile_rdl(RDL, peers), 0x1000)
                self.assertEqual(len(regs), peers+1)
                self.assertEqual([int(x["offset"], 0) for x in regs],
                                 list(range(0, (peers+1)*4, 4)))
                self.assertEqual(regs[0]["fields"][0]["mask"],
                                 f"0x{((1 << peers)-1):08x}")
                self.assertEqual(regs[-1]["fields"][0]["mask"], "0xffffffff")
                generated = header(regs)
                self.assertIn("SOC_BOOT_RESET_CTRL_CPU_RELEASE_OFFSET", generated)
                self.assertIn("SOC_BOOT_RESET_CTRL_SECONDARY_ACK_0_OFFSET", generated)
                self.assertNotIn("hardware passed", generated)

    def test_changed_sw_access_reset_or_backdoor_permission_is_rejected(self):
        source = RDL.read_text()
        release = "sw = rw;\n            hw = r;\n            reset = 0;\n            csr_backdoor_policy = \"frontdoor_only\";"
        self.assertIn(release, source)
        changes = [
            ("sw = r;", "software field ABI drift"),
            ("sw = w;", "software field ABI drift"),
            ("reset = 1;", "software field ABI drift"),
            ('csr_backdoor_policy = "backdoor_read_only";', "software field ABI drift"),
        ]
        for changed, message in changes:
            mutated = source.replace(release, release.replace(
                changed.split(" = ")[0] + " = " + (
                    "rw;" if changed.startswith("sw") else
                    "0;" if changed.startswith("reset") else
                    '"frontdoor_only";'),
                changed), 1)
            # Mutate exactly the release field, preserving a syntactically
            # legal SystemRDL description whose generated ABI is incompatible.
            self.assertNotEqual(mutated, source)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/"mutated.rdl"
                path.write_text(mutated)
                root = compile_rdl(path, 1)
                with self.subTest(changed=changed), self.assertRaisesRegex(CsrError, message):
                    register_layout(root, 0x1000)

    def test_unqualified_register_aperture_rejected(self):
        with self.assertRaisesRegex(CsrError, "exceeds SoC CSR aperture"):
            register_layout(compile_rdl(RDL, 1), 4)


if __name__ == "__main__":
    unittest.main()
