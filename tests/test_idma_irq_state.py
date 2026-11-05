"""Compile portable firmware IRQ state helper; does not claim real IRQ RTL."""
import ctypes
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class State(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ("expected_mask", "observed_mask", "acknowledged_mask",
                 "invalid_ack_mask")]


class IdmaIrqStateTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_two_engine_irq_completion_and_invalid_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"irq.so"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-shared", "-fPIC", "-o", str(out),
                            str(ROOT/"sw/dma/idma_irq_state.c")], check=True)
            lib = ctypes.CDLL(str(out))
            lib.soc_idma_irq_init.argtypes = [ctypes.POINTER(State), ctypes.c_uint32]
            lib.soc_idma_irq_sample.argtypes = [ctypes.POINTER(State), ctypes.c_uint32]
            lib.soc_idma_irq_ack.argtypes = [ctypes.POINTER(State), ctypes.c_uint32]
            lib.soc_idma_irq_complete.argtypes = [ctypes.POINTER(State)]
            lib.soc_idma_irq_complete.restype = ctypes.c_int
            state = State()
            lib.soc_idma_irq_init(ctypes.byref(state), 3)
            lib.soc_idma_irq_sample(ctypes.byref(state), 1)
            lib.soc_idma_irq_ack(ctypes.byref(state), 1)
            self.assertEqual(lib.soc_idma_irq_complete(ctypes.byref(state)), 0)
            lib.soc_idma_irq_sample(ctypes.byref(state), 2)
            lib.soc_idma_irq_ack(ctypes.byref(state), 2)
            self.assertEqual(lib.soc_idma_irq_complete(ctypes.byref(state)), 1)
            lib.soc_idma_irq_ack(ctypes.byref(state), 4)
            self.assertEqual(lib.soc_idma_irq_complete(ctypes.byref(state)), 0)


if __name__ == "__main__":
    unittest.main()
