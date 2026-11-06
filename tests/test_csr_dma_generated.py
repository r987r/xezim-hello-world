"""Guard software-only generated DMA CSR offsets against live RTL semantics."""
import unittest
from pathlib import Path
from tools.csr_dma_header import SOURCE, HEADER, compile_contract, render

ROOT = Path(__file__).resolve().parents[1]


class DmaCsrGeneratedTests(unittest.TestCase):
    def test_exact_generated_c_header(self):
        regs=compile_contract(SOURCE)
        self.assertEqual(HEADER.read_text(),render(regs))
        self.assertEqual([r['offset'] for r in regs],[0,4,8,12])
        self.assertEqual([r['name'] for r in regs],['head_lo','head_hi','command','status'])

    def test_existing_rtl_ownership_and_status_bits(self):
        rtl=(ROOT/'rtl/adapters/soc_dma_regs.sv').read_text()
        expected=(
            ".RegNumBytes(16)", ".AxiReadOnly(16'hf000)",
            "regs_d[12][0] = state_q != READY;",
            "regs_d[12][1] = irq_pending_q;",
            "regs_d[12][2] = submission_error_q;",
            "regs_d[12][3] = irq_raw_i;",
            "if (regs_q[8][0])", "else if (regs_q[8][1])",
            "regs_q[7], regs_q[6], regs_q[5], regs_q[4]",
        )
        for signature in expected:
            with self.subTest(signature=signature):
                self.assertIn(signature,rtl)
        self.assertIn('axi_lite_regs #(',rtl)
        self.assertNotIn('soc_boot_reset_ctrl_regblock',rtl)

    def test_driver_consumes_generated_constants_only(self):
        header=(ROOT/'sw/dma/dma.h').read_text()
        self.assertIn('include "../generated/soc_dma_shim_regs.h"',header)
        for name in ('HEAD_LO','HEAD_HI','COMMAND','STATUS'):
            self.assertIn(f'SOC_DMA_REG_{name}       ',header)
            self.assertNotIn(f'#define SOC_DMA_REG_{name}       0x',header)
        self.assertIn('SOC_DMA_COMMAND_IRQ_ACK_MASK',header)


if __name__=='__main__':
    unittest.main()
