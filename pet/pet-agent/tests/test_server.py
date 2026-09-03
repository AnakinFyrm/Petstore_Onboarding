"""Tests for the MCP tools.

The tools are exercised directly (they are plain functions) and once through the
server's registry, so a tool that is written but never registered is caught.
"""

import hashlib

from pet_agent.server import mcp, sha256_checksum, word_count


def test_word_count_counts_text() -> None:
    assert word_count("hello world") == {"characters": 11, "words": 2, "lines": 1}


def test_word_count_handles_multiple_lines() -> None:
    assert word_count("one\ntwo\nthree")["lines"] == 3


def test_word_count_handles_empty_text() -> None:
    assert word_count("") == {"characters": 0, "words": 0, "lines": 0}


def test_checksum_matches_hashlib() -> None:
    assert sha256_checksum("payload") == hashlib.sha256(b"payload").hexdigest()


def test_checksum_is_stable() -> None:
    assert sha256_checksum("payload") == sha256_checksum("payload")


async def test_tools_are_registered() -> None:
    names = {tool.name for tool in await mcp.list_tools()}
    assert {"word_count", "sha256_checksum"} <= names
