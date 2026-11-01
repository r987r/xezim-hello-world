.PHONY: test run help

help:
	@echo 'make test  - fetch/build Xezim 0.11.3, then run the self-checking testbench'
	@echo 'make run   - alias for make test'
	@echo 'Set XEZIM_BIN=/path/to/xezim to use an existing simulator build.'

test:
	bash ./scripts/run.sh

run: test
