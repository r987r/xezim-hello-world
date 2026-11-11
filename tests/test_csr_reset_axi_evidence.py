"""Real CPU Config-NoC reset/ACK accepted-read evidence negative tests."""
import copy
import unittest

from tools.csr_reset_axi_evidence import verify, ResetCsrEvidenceError

BASE=0x40000000


def row(offset, value, *, uid):
    return {
        "uid": uid, "monitor": "compute0_local_config.cpu",
        "plane": "config", "role": "initiator", "operation": "read",
        "address": hex(BASE+offset), "status": "complete", "issues": [],
        "expected_beats":1, "response":"0x0",
        "request":{"size":"0x2","len":"0x0"},
        "beats":[{"data":hex(value),"resp":"0x0","last":"0x1"}]
    }


class CsrResetAxiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows=[row(0,1,uid="release"),row(4,0,uid="poll"),
                   row(4,1,uid="ack")]

    def test_real_completed_release_and_ack_while_allowing_earlier_ack_poll(self):
        proof=verify(self.rows,[],BASE)
        self.assertTrue(proof["frontdoor_axi_completed"])
        self.assertFalse(proof["backdoor_equivalence_proven"])
        self.assertEqual(proof["release_read_count"],1)
        self.assertEqual(proof["ack_read_count"],2)

    def test_missing_bad_response_wrong_bus_or_no_ack_one_rejected(self):
        for modification in ("missing","bad_response","wrong_bus","no_ack_one","truncated","error"):
            rows=copy.deepcopy(self.rows)
            if modification=="missing": rows.pop()
            elif modification=="bad_response": rows[-1]["response"]="0x2"
            elif modification=="wrong_bus": rows[-1]["plane"]="data"
            elif modification=="no_ack_one": rows[-1]["beats"][0]["data"]="0x0"
            elif modification=="truncated": rows[-1]["expected_beats"]=2
            else: rows[-1]["issues"]=["unresolved"]
            with self.subTest(modification=modification),self.assertRaises(ResetCsrEvidenceError):
                verify(rows,[],BASE)

    def test_incomplete_capture_and_unsupported_address_fail_closed(self):
        with self.assertRaisesRegex(ResetCsrEvidenceError, "incomplete"):
            verify(self.rows,[{"message":"incomplete read"}],BASE)
        with self.assertRaises(ResetCsrEvidenceError):
            verify(self.rows,[],BASE+0x100)

if __name__=="__main__":
    unittest.main()
