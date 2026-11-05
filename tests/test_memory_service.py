"""Contract tests: allocation != init, providers are mutually explicit.

These use a pure in-memory fake to exercise the SAME service called later
from cocotb; no RTL performance is inferred from host timings.
"""
import unittest

from tools.memory_plan import VirtualRegion
from tools.memory_service import (
    AxiFrontdoor, HostSparseMemory, CombinedMemoryProvider, MemoryAccessError, MemoryMismatch,
    MemoryService, Pattern,
)


class DummyProvider:
    def __init__(self, base, size=4096, *, validated=True, frontdoor=True):
        self.base = base
        self.storage = bytearray(size)
        self.validated_backdoor = validated
        self.frontdoor_available = frontdoor
        self.calls = []

    async def _read(self, phys, size, method):
        off = phys - self.base
        self.calls.append((method, "read", phys, size))
        return bytes(self.storage[off:off+size])

    async def _write(self, phys, data, method):
        off = phys - self.base
        self.calls.append((method, "write", phys, len(data)))
        self.storage[off:off+len(data)] = data

    async def frontdoor_read(self, phys, size):
        return await self._read(phys, size, "frontdoor")

    async def frontdoor_write(self, phys, data):
        await self._write(phys, data, "frontdoor")

    async def backdoor_read(self, phys, size):
        return await self._read(phys, size, "backdoor")

    async def backdoor_write(self, phys, data):
        await self._write(phys, data, "backdoor")


class MemoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.base = 0x140000100
        self.region = VirtualRegion("memory0.ddr0", "ddr", self.base, 4096, False)
        self.backend = DummyProvider(self.base)
        self.cycles = 0
        self.svc = MemoryService({"memory0.ddr0": self.region}, chunk_bytes=13,
                                 cycle_counter=lambda: self.cycles)
        self.svc.register("memory0.ddr0", self.backend)
        self.a = self.svc.allocate("memory0.ddr0", 91, 64,
                                   owner="CPU0", phase="run")

    async def test_alloc_does_not_modify_backing_and_uninitialized_check_fails(self):
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.backend.storage[:100], bytes(100))
        with self.assertRaisesRegex(MemoryAccessError, "without explicit initialization"):
            await self.svc.check(self.a, Pattern("constant", 0))
        self.assertEqual(self.backend.calls, [])

    async def test_fast_auto_is_chunked_and_does_not_emit_frontdoor_traffic(self):
        p = Pattern("counter8", seed=0x37)
        self.cycles = 5
        init = await self.svc.initialize(self.a, p, policy="auto")
        self.assertEqual(init.method, "backdoor")
        self.assertEqual(init.bytes, 91)
        self.assertEqual(init.simulated_cycles, 0)
        self.assertEqual(len(self.backend.calls), 7)
        self.assertTrue(all(c[0] == "backdoor" for c in self.backend.calls))
        checked = await self.svc.check(self.a, p, policy="fast")
        self.assertEqual(checked.method, "backdoor")
        self.assertEqual(checked.bytes, 91)
        self.assertEqual(self.backend.storage[:91], p.chunk(self.a.phys, 91))
        self.assertEqual(len(self.svc.events), 2)

    async def test_strict_and_hybrid_require_both_access_paths_where_relevant(self):
        p = Pattern("address_xor", seed=0x9ab1)
        await self.svc.initialize(self.a, p, policy="strict")
        self.backend.calls.clear()
        e = await self.svc.check(self.a, p, policy="hybrid", sample_bytes=9)
        self.assertEqual(e.method, "backdoor+frontdoor-sample")
        self.assertEqual([c[0] for c in self.backend.calls].count("frontdoor"), 2)
        self.assertTrue(all(c[3] <= 13 for c in self.backend.calls))
        self.backend.validated_backdoor = False
        with self.assertRaisesRegex(MemoryAccessError, "validated backdoor"):
            await self.svc.check(self.a, p, policy="hybrid")
        e = await self.svc.check(self.a, p, policy="auto")
        self.assertEqual(e.method, "frontdoor")

    async def test_mismatch_carries_physical_address_and_no_implicit_poison(self):
        p = Pattern("constant", seed=0xa5)
        await self.svc.initialize(self.a, p)
        self.backend.storage[17] ^= 0xff
        with self.assertRaisesRegex(MemoryMismatch, hex(self.a.phys + 17)):
            await self.svc.check(self.a, p)
        # A failed check cannot create a passing 'check' event.
        self.assertEqual([e.operation for e in self.svc.events], ["init"])

    async def test_partial_coverage_invalid_handle_and_release(self):
        p = Pattern("counter8", 0)
        await self.svc.initialize(self.a, p, offset=3, size=25)
        with self.assertRaisesRegex(MemoryAccessError, "without explicit"):
            await self.svc.check(self.a, p)
        await self.svc.check(self.a, p, offset=3, size=25)
        with self.assertRaises(ValueError):
            await self.svc.initialize(self.a, p, size=92)
        with self.assertRaises(RuntimeError):
            self.svc.release(self.a, consumers_quiesced=False)
        self.svc.release(self.a, consumers_quiesced=True)
        with self.assertRaises(MemoryAccessError):
            await self.svc.initialize(self.a, p)

    async def test_unknown_method_unvalidated_backdoor_and_missing_provider(self):
        self.backend.validated_backdoor = False
        self.backend.frontdoor_available = False
        with self.assertRaisesRegex(MemoryAccessError, "no verified access"):
            await self.svc.initialize(self.a, Pattern())
        with self.assertRaisesRegex(MemoryAccessError, "validated backdoor"):
            await self.svc.initialize(self.a, Pattern(), policy="fast")
        with self.assertRaisesRegex(MemoryAccessError, "frontdoor required"):
            await self.svc.initialize(self.a, Pattern(), policy="strict")
        with self.assertRaises(ValueError):
            await self.svc.initialize(self.a, Pattern(), policy="oops")
        with self.assertRaises(ValueError):
            Pattern("no-such-mode", 5)

    async def test_backdoor_must_pass_reciprocal_frontdoor_proof(self):
        front = DummyProvider(self.base, validated=False, frontdoor=True)
        rear = front  # shared store for the valid backing case
        provider = CombinedMemoryProvider(front, rear)
        self.svc.register("memory0.ddr0", provider)
        with self.assertRaisesRegex(MemoryAccessError, "validated backdoor"):
            await self.svc.initialize(self.a, Pattern(), policy="fast")
        initial = bytes(front.storage[:32])
        with self.assertRaisesRegex(MemoryAccessError, "quiescent"):
            await provider.validate_backdoor(self.base, consumers_quiesced=False)
        await provider.validate_backdoor(self.base, consumers_quiesced=True, width=32)
        self.assertTrue(provider.validated_backdoor)
        self.assertEqual(bytes(front.storage[:32]), initial)
        e = await self.svc.initialize(self.a, Pattern("counter8"), policy="fast")
        self.assertEqual(e.method, "backdoor")

    async def test_bad_backdoor_mapping_is_rejected(self):
        front = DummyProvider(self.base, validated=False)
        wrong = DummyProvider(self.base+8, validated=False)
        provider = CombinedMemoryProvider(front, wrong)
        with self.assertRaises(MemoryMismatch):
            await provider.validate_backdoor(self.base, consumers_quiesced=True)
        self.assertFalse(provider.validated_backdoor)

    async def test_recipe_invariant_across_chunks_and_high_addresses(self):
        for p in [Pattern("constant", 0x5a), Pattern("counter8", 17),
                  Pattern("address_xor", 0xdeadbeef)]:
            full = p.chunk(self.base, 91)
            self.assertEqual(
                full, b"".join(p.chunk(self.base + off, min(7, 91-off))
                               for off in range(0, 91, 7)))
        with self.assertRaises(ValueError):
            Pattern("counter8", -1)
        with self.assertRaises(ValueError):
            Pattern("counter8", 1 << 32)


if __name__ == "__main__":
    unittest.main()
