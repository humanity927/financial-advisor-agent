from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.integration
def test_real_stdio_server_lists_and_calls_tools(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "FINANCE_PROJECT_ROOT": str(root),
        "FINANCE_CACHE_DIR": str(tmp_path),
        "FINANCE_FORCE_FIXTURE": "1",
    }

    async def run() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "finance_advisor.mcp_server"],
            env=environment,
        )
        async with (
            stdio_client(parameters) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {
                "finance_health",
                "get_market_snapshot",
                "assess_investor_profile",
                "analyze_asset_risk",
                "analyze_portfolio_risk",
                "build_allocation",
            }
            result = await session.call_tool(
                "get_market_snapshot",
                {"symbols": ["510300"]},
            )
            assert result.isError is not True
            text_blocks = [block.text for block in result.content if hasattr(block, "text")]
            payload = json.loads(text_blocks[0])
            assert payload["ok"] is True
            assert payload["meta"]["source"] == "fixture"

            portfolio_result = await session.call_tool(
                "analyze_portfolio_risk",
                {
                    "weights_pct": {"510300": 60.0, "511010": 40.0},
                    "lookback_days": 80,
                },
            )
            assert portfolio_result.isError is not True
            portfolio_blocks = [
                block.text for block in portfolio_result.content if hasattr(block, "text")
            ]
            portfolio_payload = json.loads(portfolio_blocks[0])
            assert portfolio_payload["ok"] is True
            assert (
                portfolio_payload["data"]["portfolio"]["portfolio_metrics"]["observation_count"]
                == 81
            )

    asyncio.run(run())
