"""Queue programming oracle + ABI tests. No invented RTL/DMA evidence."""
import unittest
from tools.ethernet_queue_api import (
    REG, Policy, QueueProgrammer, RxDescriptor, TxDescriptor,
    possible_overlap, select_policy,
)


class QueueApiTests(unittest.TestCase):
    def setUp(self):
        self.regs = {REG["MAGIC"]: 0x45544851,
                     REG["VERSION"]: 0x00010000,
                     REG["CAPS"]: 0x04040101,
                     REG["ENABLE"]: 0}
        self.api = QueueProgrammer(lambda a: self.regs.get(a, 0),
                                   lambda a, v: self.regs.__setitem__(a, v))

    def test_descriptors_and_64bit_addresses(self):
        rx = RxDescriptor(0x140000000, 2048, 23)
        tx = TxDescriptor(0x100000000, 73, 24)
        self.assertEqual(len(rx.encode()), 32)
        self.assertEqual(len(tx.encode()), 32)
        self.assertEqual(int.from_bytes(rx.encode()[:8], "little"), 0x140000000)
        self.assertEqual(int.from_bytes(tx.encode()[8:12], "little"), 73)
        for bad in ((0xffffffffffffffff, 2, 3), (0, 0, 3)):
            with self.assertRaises(ValueError):
                RxDescriptor(*bad)

    def test_overlap_detected_before_programming(self):
        a = Policy(0x0800, 0xffff, 6000, 0xffff, True, 0)
        b = Policy(0x0800, 0xffff, 6001, 0xffff, True, 0)
        c = Policy(0x0800, 0xffff, 6000, 0xffff, True, 0)
        self.assertFalse(possible_overlap(a, b))
        self.assertTrue(possible_overlap(a, c))
        self.assertEqual(select_policy([a, b], ethertype=0x0800,
                           is_udp=True, udp_dst_port=6001), 1)
        with self.assertRaisesRegex(ValueError, "MULTI_MATCH"):
            select_policy([a,c],ethertype=0x0800,
                          is_udp=True,udp_dst_port=6000)
        self.api.config_policy(0, a)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            self.api.config_policy(1, c, existing=[a])
        self.api.config_policy(1,b,existing=[a])

    def test_ring_programming_and_capacity(self):
        self.api.config_ring(0, rx=True, desc_addr=0x100004000,
                             cq_addr=0x100005000)
        self.assertEqual(self.regs[REG["RX_DESC_HI"]],1)
        self.assertEqual(self.regs[REG["RX_CQ_LO"]],0x5000)
        with self.assertRaises(ValueError):
            self.api.config_ring(1, rx=True, desc_addr=0x4000,cq_addr=0x5000)
        self.api.ring_doorbell(rx=True,new_producer=16)
        with self.assertRaises(ValueError):
            self.api.ring_doorbell(rx=True,new_producer=17)
        with self.assertRaises(ValueError):
            self.api.ring_doorbell(rx=True,new_producer=0xffffffff)
        self.regs[REG["ENABLE"]] = 3
        with self.assertRaises(ValueError):
            self.api.config_ring(0, rx=False, desc_addr=0x6000,cq_addr=0x7000)


if __name__ == "__main__":
    unittest.main()
