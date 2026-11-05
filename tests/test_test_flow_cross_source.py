"""Cross-language CPU firmware/SV step capture, not a synthetic RTL pass."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tools")]
from test_flow_codec import decode_c_marker, sv_event
from test_flow_report import firmware_mmio_events, write_report


class CrossLanguageStepEvents(unittest.TestCase):
    def test_rtl_checker_markers_join_same_flow_report(self):
        with TemporaryDirectory() as tmp:
            output=Path(tmp)
            (output/"simulation.log").write_text(
                "\n".join(f"SOC_FLOW_V1|{i*10}|{phase}|cpu0|firmware_{phase}|{status}"
                          for i,(phase,status) in enumerate((
                              ("init","start"),("init","pass"),
                              ("run","start"),("run","pass"),
                              ("check","start"),("check","pass")),1)))
            required={phase:["cpu0.firmware_"+phase] for phase in ("init","run","check")}
            result=write_report(output,{"report":{"flow":{"required_steps":required}}})
            self.assertTrue(result["passed"],result["issues"])
            self.assertEqual(len(result["rows"]),3)
            self.assertEqual([r["origin"] for r in result["rows"]],["rtl_observed"]*3)

    def test_c_marker_compiles_and_roundtrips_all_phases(self):
        compiler=shutil.which("cc")
        if compiler is None:
            self.skipTest("host C compiler unavailable")
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"test.c"
            source.write_text(
                '#include <stdio.h>\n#include "sw/common/test_flow.h"\n'
                'int main(void){ volatile unsigned sink=0;\n'
                'soc_flow_emit(&sink,SOC_FLOW_RUN,SOC_FLOW_PASS,7,101);\n'
                'printf("%08x\\n",(unsigned)sink);return 0; }\n')
            program=root/"test-flow-c"
            subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                            "-I",str(ROOT),str(source),"-o",str(program)],check=True)
            code=int(subprocess.check_output([str(program)],text=True).strip(),16)
            self.assertEqual(decode_c_marker(code,{7:"cpu0"},{101:"dma_check"}),
                             {"phase":"run","status":"pass","actor":"cpu0","step":"dma_check"})
            with self.assertRaisesRegex(ValueError,"unknown C"):
                decode_c_marker(0,{7:"cpu0"},{101:"dma_check"})

    def test_real_axi_completion_required_for_c_step(self):
        with TemporaryDirectory() as tmp:
            out=Path(tmp)
            address=0x10000f00
            def transaction(word, *, strobe="0xf",response="0x0"):
                return {"monitor":"compute0_local_data.cpu","operation":"write",
                        "address":hex(address),"status":"complete","response":response,
                        "request":{},"beats":[{"data":hex(word),"strb":strobe,
                                               "time_ps":120000}]}
            encoded=0xf1000000 | (1<<22) | (1<<20) | (7<<12) | 101
            payload={"run":{"capture_bound":True,"capture_overflow":False},
                     "sections":{"axi":{"transactions":[transaction(encoded)]}}}
            (out/"axi-transactions.json").write_text(json.dumps(payload))
            cfg={"monitor":"compute0_local_data.cpu","address":hex(address),
                 "actors":{"7":"cpu0"},"steps":{"101":"dma_check"}}
            rows=firmware_mmio_events(out,cfg)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["origin"],"rtl_observed")
            self.assertEqual(rows[0]["status"],"pass")
            for problem in ("partial","slverr","capture"):
                changed=json.loads(json.dumps(payload))
                if problem=="partial":
                    changed["sections"]["axi"]["transactions"][0]["beats"][0]["strb"]="0x3"
                elif problem=="slverr":
                    changed["sections"]["axi"]["transactions"][0]["response"]="0x2"
                else:
                    changed["run"]["capture_overflow"]=True
                (out/"axi-transactions.json").write_text(json.dumps(changed))
                with self.subTest(problem=problem),self.assertRaises(ValueError):
                    firmware_mmio_events(out,cfg)

    def test_sv_emitter_rejects_invalid_name(self):
        self.assertIn("SOC_FLOW_V1",sv_event("init","cpu0","dma_hook","start"))
        with self.assertRaises(ValueError):
            sv_event("init","cpu0","bad'\\n$finish","pass")


if __name__=="__main__":
    unittest.main()
