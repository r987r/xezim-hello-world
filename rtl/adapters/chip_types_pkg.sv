`include "axi/typedef.svh"
package chip_types_pkg;
  typedef logic [31:0] addr32_t;
  typedef logic [63:0] addr64_t;
  typedef logic [31:0] data32_t;
  typedef logic [3:0] strb32_t;
  typedef logic [3:0] data_id_t;
  typedef logic user_t;
  `AXI_LITE_TYPEDEF_ALL(lite, addr32_t, data32_t, strb32_t)
  // Same address/ID fields as the data NoC, before upstream data upsizing.
  `AXI_TYPEDEF_ALL(narrow, addr64_t, data_id_t, data32_t, strb32_t, user_t)
endpackage
