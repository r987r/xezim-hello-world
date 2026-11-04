"""Fast host/Cross-RV32I preflight for compiler runtime glue."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "sw/common/rv32i_runtime.c"
HOST_SOURCE = """
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
int32_t __mulsi3(int32_t, int32_t);
void *memset(void *, int, size_t);
int main(void) {
 const int32_t a[] = {0, 1, -1, 2, -2, INT32_MAX, INT32_MIN, 12345, -23456};
 for (unsigned i=0; i<sizeof(a)/sizeof(a[0]); ++i)
   for (unsigned j=0; j<sizeof(a)/sizeof(a[0]); ++j)
     assert((uint32_t)__mulsi3(a[i],a[j]) ==
       (uint32_t)((uint64_t)(uint32_t)a[i]*(uint32_t)a[j]));
 unsigned char mem[40];
 for (int i=0;i<40;++i) mem[i]=0x5a;
 assert(memset(mem+3,0xbc,31)==mem+3);
 for (int i=0;i<40;++i) assert(mem[i]==((i>=3&&i<34)?0xbc:0x5a));
 return 0;
}
"""


class Rv32iRuntimeTests(unittest.TestCase):
    def test_host_helpers(self):
        cc = shutil.which("cc")
        if not cc:
            self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t/"test.c").write_text(HOST_SOURCE)
            subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra",
                            "-Werror", "-fno-builtin", str(RUNTIME),
                            str(t/"test.c"), "-o", str(t/"test")],
                           capture_output=True, text=True, check=True)
            subprocess.run([str(t/"test")], capture_output=True, check=True)

    def test_freestanding_riscv_link(self):
        clang = shutil.which("clang")
        if not clang or not shutil.which("ld.lld"):
            self.skipTest("LLVM cross compiler/linker unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp)/"rv32i.elf"
            subprocess.run([clang, "--target=riscv32-unknown-elf",
                            "-march=rv32i", "-mabi=ilp32",
                            "-Oz", "-ffreestanding", "-fno-builtin",
                            "-nostdlib", "-fuse-ld=lld",
                            "-Wl,-Ttext=0x20001000", "-Wl,-e,__mulsi3",
                            str(RUNTIME), "-o", str(elf)],
                           capture_output=True, text=True, check=True)
            self.assertEqual(elf.read_bytes()[:6], b"\x7fELF\x01\x01")
