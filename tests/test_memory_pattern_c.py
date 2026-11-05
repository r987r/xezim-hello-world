"""Portable C CPU pattern compatibility against the Python verification recipe."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.memory_service import Pattern

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r"""
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include "memory_pattern.h"
int main(void) {
    if (!soc_mem_pattern_valid(SOC_PATTERN_COUNTER8) ||
        !soc_mem_pattern_valid(SOC_PATTERN_CONSTANT) ||
        !soc_mem_pattern_valid(SOC_PATTERN_ADDRESS_XOR) ||
        soc_mem_pattern_valid((soc_pattern_kind_t)42))
        return 4;
    uint8_t data[37];
    const uint64_t addr = 0x140000137ull;
    for (unsigned k = 1; k <= 3; ++k) {
        soc_mem_fill_pattern(data, addr, sizeof(data), 0x1234u, (soc_pattern_kind_t)k);
        if (soc_mem_check_pattern(data, addr, sizeof(data), 0x1234u, (soc_pattern_kind_t)k) != sizeof(data))
            return 2;
        for (size_t i=0; i<sizeof(data); ++i) printf("%02x", data[i]);
        puts("");
    }
    soc_mem_fill_pattern(data, addr, sizeof(data), 0x1234u, SOC_PATTERN_COUNTER8);
    data[9] ^= 0xffu;
    return soc_mem_check_pattern(data, addr, sizeof(data), 0x1234u, SOC_PATTERN_COUNTER8) == 9 ? 0 : 3;
}
"""


class MemoryPatternCTests(unittest.TestCase):
    def test_python_and_c_patterns_are_byte_identical(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not available")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/"test.c").write_text(SOURCE)
            binary = path/"test"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-pedantic", "-I", str(ROOT/"sw/common"),
                str(ROOT/"sw/common/memory_pattern.c"), str(path/"test.c"),
                "-o", str(binary)], check=True, capture_output=True, text=True)
            got = subprocess.run([str(binary)], check=True,
                                 capture_output=True, text=True).stdout.strip().splitlines()
        expected = [
            Pattern(kind, 0x1234).chunk(0x140000137, 37).hex()
            for kind in ("counter8", "constant", "address_xor")]
        self.assertEqual(got, expected)
