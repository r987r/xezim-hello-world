.PHONY: dv-memory-service bench-memory help gen check-generated check-config dv-memory dv-memory-negative dv-cpu dv-serv dv-sram dv-boot dv-supernoc dv-chip dv-chip-dma dv-chip-cpu-dma dv-chip-ddr4-real dv-dma dv-dma-vectors smoke test test-xezim test-noc test-list

help:
	@echo 'make gen             Generate tracked RTL, firmware and documentation'
	@echo 'make check-generated Check exact generated file/content drift'
	@echo 'make check-config    Run configuration/generator/runner unit tests'
	@echo 'make dv-memory-service  Fast common INIT/CHECK and C-pattern tests'
	@echo 'make bench-memory       Labelled synthetic service timings, not RTL performance'
	@echo 'make test-list       List every YAML-defined regression target'
	@echo 'make test            Full suite: all profiles, diagnostics and both simulators'
	@echo 'make test-xezim      CPU, SRAM and default/full/sparse memory traffic'
	@echo 'make test-noc        Verilator NoC elaboration, traffic and negative check'
	@echo 'make dv-boot         Real cold boot (BOOT_WAVE=1 BOOT_TRACE=1 for debug)'
	@echo 'make dv-chip         Chip boot + integrated DMA regression through real FlooNoCs'
	@echo 'make dv-chip-dma     SS0 and SS1 DMA via data/config NoCs; host preloads only DMA-only SRAM'
	@echo 'make dv-chip-cpu-dma Run compiled CPU0 C DMA with cold boot, shared INIT/RUN/CHECK and AXI reports'
	@echo 'make dv-chip-ddr4-real  Opt-in pinned LiteDRAM RTL + DFI CPU/iDMA via both NoCs'
	@echo 'make dv-dma-vectors  Generate 100-descriptor DMA SRAM and expected-data manifest (host only)'
	@echo 'make dv-dma          Run real pinned PULP DMA frontend/backend AXI transfer test'
	@echo 'python3 tools/regress.py --help    Filelist/build/run stages and target selection'

gen:
	python3 tools/generate.py

check-generated:
	python3 tools/generate.py --check

check-config:
	python3 -m unittest discover -s tests -v

test-list:
	python3 tools/regress.py full --list

dv-memory:
	python3 tools/regress.py memory $(if $(AXI_CONFIG),--memory-config $(AXI_CONFIG))

dv-memory-negative:
	python3 tools/regress.py memory-negative

dv-cpu:
	python3 tools/regress.py cpu-fetch

dv-sram:
	python3 tools/regress.py sram

dv-serv:
	python3 tools/regress.py serv

dv-boot:
	python3 tools/regress.py boot $(if $(filter 1,$(BOOT_WAVE)),--arg=--wave --arg=+BOOT_WAVE) $(if $(filter 1,$(BOOT_TRACE)),--arg=+BOOT_TRACE)

dv-supernoc:
	python3 tools/regress.py supernoc

dv-chip:
	python3 tools/regress.py chip $(if $(filter 1,$(FAST_FAIL)),--fail-fast)

dv-chip-dma:
	python3 tools/regress.py chip-dma

dv-chip-cpu-dma:
	python3 tools/regress.py chip-cpu-dma

dv-chip-ddr4-real:
	python3 tools/regress.py chip-ddr4-real

dv-dma:
	python3 tools/regress.py dma

dv-dma-vectors:
	python3 tools/dma_vectors.py --count 100 --length 64

smoke:
	python3 tools/regress.py smoke

test-xezim: check-config check-generated
	python3 tools/regress.py xezim

test-noc: check-generated
	python3 tools/regress.py noc

test: check-config check-generated
	python3 tools/regress.py full

dv-memory-service:
	python3 -m unittest tests.test_memory_service tests.test_memory_pattern_c tests.test_memory_benchmark tests.test_memory_report -v

bench-memory:
	python3 tools/memory_benchmark.py --out .tools/benchmarks/memory.json
