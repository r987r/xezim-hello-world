import unittest
from tools.memory_rtl_window import RtlMemoryWindow
from tools.memory_service import MemoryAccessError


class RtlMemoryWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_real_hook_and_is_never_implicitly_validated(self):
        window = RtlMemoryWindow(0x140000000, 4096)
        self.assertFalse(window.validated_backdoor)
        self.assertFalse(window.frontdoor_available)
        with self.assertRaisesRegex(MemoryAccessError, "not bound"):
            await window.backdoor_read(window.base, 1)

    async def test_ranges_quiescence_and_readback(self):
        mem = bytearray(64)
        idle = [False]
        async def read(offset, count):
            return mem[offset:offset+count]
        async def write(offset, data):
            mem[offset:offset+len(data)] = data
        window = RtlMemoryWindow(0x100000000, 64,
                                 read_hook=read, write_hook=write,
                                 quiescent=lambda: idle[0],
                                 implementation="test_fake_not_RTL")
        with self.assertRaisesRegex(MemoryAccessError, "not quiescent"):
            await window.backdoor_read(window.base, 4)
        idle[0] = True
        await window.backdoor_write(window.base+60, b"abcd")
        self.assertEqual(await window.backdoor_read(window.base+60, 4), b"abcd")
        with self.assertRaisesRegex(MemoryAccessError, "crosses"):
            await window.backdoor_read(window.base+63, 2)
        with self.assertRaises(MemoryAccessError):
            await window.frontdoor_read(window.base, 1)
        self.assertFalse(window.validated_backdoor)

    async def test_partial_read_fails(self):
        async def short_read(off, size):
            return b""
        async def no_op(off, data):
            return None
        window = RtlMemoryWindow(0, 10, read_hook=short_read,
                                 write_hook=no_op, quiescent=lambda: True)
        with self.assertRaisesRegex(MemoryAccessError, "incomplete"):
            await window.backdoor_read(0, 3)


if __name__ == "__main__":
    unittest.main()
