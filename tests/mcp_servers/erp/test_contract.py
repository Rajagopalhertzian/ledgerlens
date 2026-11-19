"""Contract tests for ERP MCP Server - pytest entry point."""

import sys
from pathlib import Path

# Add the contract tests to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

# Import all tests from contract_tests.py
from ledgerlens.mcp_servers.erp.contract_tests import *  # noqa: F403,F401

# This file exists to make pytest discover the tests in contract_tests.py
# The actual tests are defined in src/ledgerlens/mcp_servers/erp/contract_tests.py
