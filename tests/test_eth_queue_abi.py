
"""Ethernet queue ABI checks (does not simulate MAC or DMA)."""
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
HEADER=ROOT/"sw/ethernet/eth_queue_abi.h"
RTL=ROOT/"rtl/io/ethernet0/ethernet_queue_ctrl.sv"
class QueueABITests(unittest.TestCase):
    def test_c_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"abi.c"
            file.write_text('#include "eth_queue_abi.h"\nint main(void){return 0;}\n')
            subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                            "-pedantic","-I",str(HEADER.parent),
                            "-fsyntax-only",str(file)],check=True)
    def test_register_offsets(self):
        defs=re.findall(r"#define\s+(ETHQ_REG_\w+)\s+0x([0-9a-f]+)u",
                        HEADER.read_text())
        self.assertGreaterEqual(len(defs),25)
        rtl=RTL.read_text()
        for name,value in defs:
            self.assertRegex(rtl,rf"8'h{int(value,16):02x}\s*:",name)
        for param in ("RX_QUEUES = 1","TX_QUEUES = 1","POLICY_ENTRIES = 4"):
            self.assertIn(param,rtl)
if __name__=="__main__":unittest.main()
