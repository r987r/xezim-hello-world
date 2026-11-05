# Generated SoC reference

Do not edit. Run `make gen` to atomically regenerate this tree from `config/soc.yaml`. All output files are version-controlled for diffs.

The `memory/` SystemVerilog and `boot/` firmware images are executable in separate scoped testbenches. All configured local/global FlooNoC networks have checked-in structural SystemVerilog in noc/floonoc. supernoc/supernoc_tb.sv connects them with upstream AXI BFMs; run make dv-supernoc for current-source routed-traffic verification. chip/ contains the actual CPU/NoC boot configuration, phased firmware and shared checker; run make dv-chip. Optional real iDMA/CSR wiring and CPU0 C-DMA integration are verified with behavioral DDR/HBM models; physical controllers/PHYs and CPU IRQ handlers are separate integration work.
