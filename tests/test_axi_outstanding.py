"""Passive quiescence does not weaken the canonical AXI transaction checker."""
import unittest

from dv.common.axi_outstanding import AcceptedAxiInFlight


def event(channel, monitor="compute0_local_data.cpu", axi_id="0x0", last="0x1", active=0):
    return {"channel":channel, "monitor":monitor,
            "active":active, "fields":{"id":axi_id, "last":last}}


class AcceptedAxiInFlightTests(unittest.TestCase):
    def test_read_requires_last_and_write_requires_b(self):
        tracker=AcceptedAxiInFlight()
        tracker.observe(event("ar"))
        tracker.observe(event("aw",axi_id="0x2"))
        tracker.observe(event("r",last="0x0"))
        self.assertFalse(tracker.is_idle())
        tracker.observe(event("r",last="0x1"))
        self.assertFalse(tracker.is_idle())
        tracker.observe(event("b",axi_id="0x2"))
        self.assertTrue(tracker.is_idle())

    def test_multi_id_and_boundaries_and_reset(self):
        tracker=AcceptedAxiInFlight()
        tracker.observe(event("ar",axi_id="0x1"))
        tracker.observe(event("ar",axi_id="0x1"))
        tracker.observe(event("ar",monitor="compute1_local_data.cpu",axi_id="0x1"))
        for _ in range(2):
            tracker.observe(event("r",axi_id="0x1"))
        self.assertFalse(tracker.is_idle())
        tracker.observe(event("r",monitor="compute1_local_data.cpu",axi_id="0x1"))
        self.assertTrue(tracker.is_idle())
        tracker.observe(event("aw"))
        tracker.observe(event("reset",active=1))
        self.assertTrue(tracker.is_idle())

    def test_orphan_response_never_reports_idle(self):
        tracker=AcceptedAxiInFlight()
        tracker.observe(event("r"))
        self.assertFalse(tracker.is_idle())
        self.assertEqual(len(tracker.summary()["unmatched"]),1)

    def test_completeness_gate_fails_if_polling_cpu_read_not_done(self):
        tracker=AcceptedAxiInFlight()
        tracker.observe(event("ar",monitor="compute0_local_data.cpu"))
        tracker.observe(event("ar",monitor="compute0_local_data.dma"))
        tracker.observe(event("r",monitor="compute0_local_data.dma"))
        self.assertFalse(tracker.is_idle())
        self.assertEqual(tracker.summary()["pending"],
                         [["compute0_local_data.cpu","read",0,1]])
        tracker.observe(event("r",monitor="compute0_local_data.cpu"))
        self.assertTrue(tracker.is_idle())


if __name__=="__main__":
    unittest.main()
