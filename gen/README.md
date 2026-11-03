# Generated SoC reference

Do not edit. Run `make gen` to atomically regenerate this tree from `config/soc.yaml`. All output files are version-controlled for diffs.

The `memory/` SystemVerilog and `boot/` firmware images are executable in separate scoped testbenches. All configured local/global FlooNoC networks have checked-in structural SystemVerilog in noc/floonoc. supernoc/supernoc_tb.sv connects them with upstream AXI BFMs; run make dv-supernoc for current-source routed-traffic verification. CPU, DMA, AXI-Lite bridges and physical controllers are separate integration work.
