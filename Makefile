.PHONY: help gen check-generated check-config dv-memory dv-memory-negative dv-cpu dv-serv dv-sram dv-boot smoke test

help:
	@echo 'make gen                Generate all tracked gen/ artifacts, FlooNoC RTL and README diagrams'
	@echo 'make check-generated    Fail on missing/changed/stale generated files'
	@echo 'make check-config       Validate architecture and generator behavior'
	@echo 'make dv-memory          Verify 2x2 AXI4 crossbar with HBM + DDR models'
	@echo 'make dv-memory-negative Prove readback checker detects corruption'
	@echo 'make dv-cpu             Optional fetch-only diagnostic (excluded from CI)'
	@echo 'make dv-sram            Exercise standalone RTL SRAM ports and byte strobes'
	@echo 'make dv-serv            Minimal standalone SERV execution (no bootloader)'
	@echo 'make dv-boot            ROM -> flash -> SRAM -> CPU1 reset release -> real firmware'
	@echo 'make test               Run checked-in generation and all RTL tests'

gen:
	python3 tools/generate.py

check-generated:
	python3 tools/generate.py --check

check-config:
	python3 -m unittest discover -s tests -v

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

dv-sram:
	bash scripts/run-local-sram.sh

dv-serv:
	bash scripts/run-serv-minimal.sh

dv-boot:
	bash scripts/run-boot.sh

smoke:
	@$${XEZIM_BIN:-xezim} -s hello_world_tb dv/smoke/hello_world_tb.sv

test: check-config check-generated dv-memory dv-memory-negative dv-serv dv-sram dv-boot
