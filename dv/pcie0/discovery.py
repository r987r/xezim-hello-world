"""Classify only expected absent-function probes during PCIe RC enumeration.

Filters the *actual* RootComplex logger object (upstream renames .name after
creating it), not a newly looked-up logging Logger with a different key.
Unexpected warning/error messages are never filtered or suppressed.
"""
import logging
from cocotb.triggers import with_timeout


class ExpectedMissingFunction(logging.Filter):
    def __init__(self):
        super().__init__()
        self.count = 0

    def filter(self, record):
        if (record.levelno == logging.WARNING
                and "Failed to route config type 0 TLP" in record.getMessage()):
            self.count += 1
            return False
        return True


async def enumerate_root_complex(rc, *, timeout_us=None):
    sentinel = ExpectedMissingFunction()
    # Critical: rc.log was created under an ID-suffixed logger name. The
    # model then rewrites rc.log.name; logging.getLogger(new_name) is NOT it.
    rc.log.addFilter(sentinel)
    try:
        if timeout_us is None:
            await rc.enumerate()
        else:
            await with_timeout(rc.enumerate(), timeout_us, "us")
    finally:
        rc.log.removeFilter(sentinel)
    return sentinel.count
