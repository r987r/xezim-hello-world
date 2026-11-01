.PHONY: help gen check-config dv-hbm dv-hbm-negative smoke test

help:
	@echo 'make check-config   Validate the SoC architecture and generator tests'
	@echo 'make gen            Generate the HBM testbench from config/soc.yaml'
	@echo 'make dv-hbm         Run real 2x2 AXI4 crossbar/HBM-model verification'
	@echo 'make dv-hbm-negative  Verify a deliberately incorrect read is detected'
	@echo 'make smoke          Run a small standalone Xezim smoke test'
	@echo 'make test           Run check-config and dv-hbm'

check-config:
	python3 -m unittest discover -s tests -v

gen:
	python3 tools/socgen.py

dv-hbm:
	bash scripts/run-dv.sh

dv-hbm-negative:
	@set -e; log=$$(mktemp); trap 'rm -f "$$log"' EXIT; \
	  if bash scripts/run-dv.sh --negative > "$$log" 2>&1; then \
	    echo 'ERROR: negative test passed unexpectedly'; cat "$$log"; exit 1; \
	  fi; \
	  grep -q 'FAIL AXI read:' "$$log" || { echo 'Negative test failed for a different reason'; cat "$$log"; exit 1; }; \
	  echo 'PASS: expected data corruption was detected'

smoke:
	@$${XEZIM_BIN:-xezim} -s hello_world_tb dv/smoke/hello_world_tb.sv

test: check-config dv-hbm
