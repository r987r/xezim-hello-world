"""Host-only frame reference tests; real MAC/GMII work remains #37."""
import unittest
from dv.ethernet0.frame_contract import Packet, encode, decode, destination_class


class FrameContractTests(unittest.TestCase):
    def setUp(self):
        self.packet = Packet(b"\x02\x00\x00\x00\x00\x01",
                             b"\x02\x00\x00\x00\x00\x02",
                             "10.0.0.1", "10.0.0.2", 1234, 4789,
                             bytes(range(200)))

    def test_udp_roundtrip_and_fast_candidate(self):
        port, payload = decode(encode(self.packet))
        self.assertEqual((port, payload), (4789, self.packet.payload))
        self.assertEqual(destination_class(port, frozenset({4789})),
                         "pcie_fast_candidate")
        self.assertEqual(destination_class(port, frozenset()), "global_memory")

    def test_corrupt_fcs_and_header_rejected(self):
        image = bytearray(encode(self.packet))
        image[-5] ^= 1
        with self.assertRaisesRegex(ValueError, "FCS"):
            decode(bytes(image))
        image = bytearray(encode(self.packet))
        image[12:14] = b"\x86\xdd"
        from zlib import crc32
        from struct import pack
        image[-4:] = pack("<I", crc32(image[:-4]) & 0xffffffff)
        with self.assertRaisesRegex(ValueError, "IPv4"):
            decode(bytes(image))

    def test_invalid_metadata(self):
        with self.assertRaises(ValueError):
            destination_class(65536, frozenset())


if __name__ == "__main__":
    unittest.main()
