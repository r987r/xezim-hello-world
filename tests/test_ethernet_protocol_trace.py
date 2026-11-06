"""GMII reporter framing semantics, no extra bus driver or protocol parser."""
from pathlib import Path
import unittest
from dv.ethernet0.frame_contract import Packet, encode
from dv.ethernet0.gmii_trace import frame_fields


class EthernetProtocolTraceTests(unittest.TestCase):
    def test_actual_frame_fields_preserve_byte_payload_and_network_headers(self):
        wire=encode(Packet(src_mac=bytes.fromhex("0250b6000011"),
                           dst_mac=bytes.fromhex("0250b6000022"),
                           src_ip="10.20.30.40",dst_ip="10.20.30.41",
                           src_port=12345,dst_port=6000,
                           payload=bytes(range(16))))[:-4]
        fields=frame_fields(wire,observed=True,fcs_valid=True)
        self.assertEqual(fields["dst_mac"],"02:50:b6:00:00:22")
        self.assertEqual(fields["src_mac"],"02:50:b6:00:00:11")
        self.assertEqual(fields["src_ip"],"10.20.30.40")
        self.assertEqual(fields["dst_ip"],"10.20.30.41")
        self.assertEqual(fields["src_port"],12345)
        self.assertEqual(fields["dst_port"],6000)
        self.assertEqual(fields["ether_type"],"0x0800")
        self.assertEqual(fields["payload_hex"],wire.hex())
        self.assertEqual(fields["length_bytes"],len(wire))
        self.assertTrue(fields["fcs_valid"])
        self.assertEqual(fields["boundary"],"gmii_tx_sink_observed")

    def test_injected_rx_never_claims_dut_accepted_it(self):
        fields=frame_fields(bytes.fromhex("0250b60000220250b60000110800"),
                            observed=False)
        self.assertEqual(fields["boundary"],"gmii_rx_source_injected")
        self.assertEqual(fields["direction"],"external_to_rtl")
        self.assertNotIn("fcs_valid",fields)


if __name__=="__main__":
    unittest.main()
