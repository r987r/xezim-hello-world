// Common SV test-flow syntax for bench-driven stimulus/checker steps.
// Captured by tools/test_flow_report.py from the real simulator transcript.
// PHASE/ACTOR/STEP/STATUS are string literals. Only emit PASS after a
// real checker verdict; $display alone is not proof of protocol behavior.
`ifndef SOC_TEST_FLOW_SVH
`define SOC_TEST_FLOW_SVH
`define SOC_FLOW_STEP(PHASE, ACTOR, STEP, STATUS) \
  $display("SOC_FLOW_V1|%0d|%s|%s|%s|%s", $time, PHASE, ACTOR, STEP, STATUS)
`endif
