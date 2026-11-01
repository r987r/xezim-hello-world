.PHONY: help gen check-config dv-memory dv-memory-negative dv-cpu smoke test

help:
	@echo 'make check-config       Validate SoC schema, NoC IR, and CPU/memory selections'
	@echo 'make gen                Generate memory testbench and vendor-neutral NoC IR'
	@echo 'make dv-memory          Verify real 2x2 AXI4 crossbar with HBM + DDR models'
	@echo 'make dv-memory-negative Confirm deliberate data corruption is detected'
	@echo 'make dv-cpu             Compile and exercise real PicoRV32 + SERV CPU RTL'
	@echo 'make smoke              Minimal Xezim test'
	@echo 'make test               Run config, memory, CPU, and negative tests'

check-config:
	python3 -m unittest discover -s tests -v

gen:
	python3 tools/socgen.py

dv-memory:
	bash scripts/run-dv.sh

dv-memory-negative:
	@set -e; log=$$(mktemp); trap 'rm -f "$$log"' EXIT; \
	  if bash scripts/run-dv.sh --negative > "$$log" 2>&1; then \
	    echo 'ERROR: negative test unexpectedly passed'; cat "$$log"; exit 1; \
	  fi; \
	  grep -q 'FAIL AXI read:' "$$log" || { echo 'Unexpected failure'; cat "$$log"; exit 1; }; \
	  echo 'PASS: expected data mismatch detected'

dv-cpu:
	bash scripts/run-cpu.sh

smoke:
	@$${XEZIM_BIN:-xezim} -s hello_world_tb dv/smoke/hello_world_tb.sv

test: check-config dv-memory dv-memory-negative dv-cpu
