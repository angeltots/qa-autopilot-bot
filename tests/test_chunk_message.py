"""Tests for the chunk_message helper in core.discord_utils."""
import sys
import os

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.discord_utils import chunk_message


class TestChunkMessageShort:
    """Messages that fit in a single chunk."""

    def test_few_items_single_chunk(self):
        header = "Header line"
        items = [f"- item {i}" for i in range(5)]
        chunks = chunk_message(header, items)
        assert len(chunks) == 1
        assert chunks[0].startswith("Header line")
        for item in items:
            assert item in chunks[0]

    def test_empty_items(self):
        chunks = chunk_message("Header", [])
        assert chunks == ["Header"]

    def test_empty_header_and_items(self):
        chunks = chunk_message("", [])
        assert chunks == []


class TestChunkMessageLong:
    """Messages that require multiple chunks."""

    def test_many_items_split_into_chunks(self):
        header = "** Created tests **"
        # Each item ~100 chars, 25 items => ~2500+ chars total
        items = [
            f"- [`TC{i:02d}`](https://app.clickup.com/t/very-long-task-id-{i:04d}) "
            f"Verify that the scenario number {i} works correctly end to end"
            for i in range(25)
        ]
        chunks = chunk_message(header, items, max_len=2000)

        # Must produce more than one chunk
        assert len(chunks) > 1

        # No chunk may exceed the limit
        for chunk in chunks:
            assert len(chunk) <= 2000, f"Chunk length {len(chunk)} exceeds 2000"

        # Header appears only in the first chunk
        assert header in chunks[0]
        for chunk in chunks[1:]:
            assert header not in chunk

        # All items must appear across all chunks (no data loss)
        combined = "\n".join(chunks)
        for item in items:
            assert item in combined, f"Missing item: {item}"

    def test_no_data_loss(self):
        header = "H"
        items = [f"item-{i}" for i in range(50)]
        chunks = chunk_message(header, items, max_len=200)
        combined = "\n".join(chunks)
        for item in items:
            assert item in combined


class TestChunkMessageEdgeCases:
    """Edge cases: oversized single items, exact boundaries."""

    def test_single_item_exceeds_max_len(self):
        header = "H"
        long_item = "X" * 3000
        chunks = chunk_message(header, [long_item])
        # The item must not be silently dropped
        combined = "\n".join(chunks)
        assert long_item in combined

    def test_every_item_present_with_oversized(self):
        header = "Header"
        items = ["short", "X" * 2500, "also short"]
        chunks = chunk_message(header, items, max_len=2000)
        combined = "\n".join(chunks)
        for item in items:
            assert item in combined

    def test_exact_boundary(self):
        # Header + newline + item exactly equals max_len
        max_len = 50
        header = "H" * 20
        item = "I" * (max_len - 20 - 1)  # -1 for the newline separator
        chunks = chunk_message(header, [item], max_len=max_len)
        assert len(chunks) == 1
        assert len(chunks[0]) == max_len
