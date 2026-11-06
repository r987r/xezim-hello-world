// SCN-3 contract smoke: checks the real SV package can compile and log
// actions selected from the same canonical plan. No AXI/DUT is driven here.
`timescale 1ns/1ps
module test_scenario_sv_adapter;
  import soc_scenario_contract_pkg::*;
  initial begin
    if (SCN_CONTRACT_VERSION != 1 || SCN_ACTION_COUNT < 2)
      $fatal(1, "scenario package missing required actions");
    if (scn_action_id(0) == "" || scn_action_phase(0) == "" ||
        scn_action_kind(0) == "" || scn_expected_id(0) == "")
      $fatal(1, "scenario package missing action metadata");
    if (scn_text_arg(0, "region") != "memory0.ddr0" ||
        scn_uint_arg(0, "size") != 64)
      $fatal(1, "SV data and region args differ from resolved scenario");
    scn_emit_driver(0, "issued", 64'd10);
    scn_emit_driver(1, "issued", 64'd11);
    scn_emit_driver(0, "driver_done", 64'd13);
    scn_emit_driver(1, "driver_done", 64'd14);
    $display("PASS SCN-3 SystemVerilog scenario metadata and driver events (no RTL proof)");
    $finish;
  end
endmodule
