"""Lightweight Discord utility helpers (no heavy dependencies)."""


def chunk_message(header: str, items: list, max_len: int = 2000) -> list:
    """Split a header + line-items message into chunks that each fit within max_len.

    Args:
        header: Text that appears at the top of the first chunk only.
        items: List of line-item strings (each becomes a separate line).
        max_len: Maximum character length per chunk (Discord default: 2000).

    Returns:
        A list of message strings.  Each string is <= max_len characters,
        except when a single item by itself exceeds max_len (it is kept
        intact rather than silently dropped).
    """
    if not items:
        return [header] if header else []

    chunks: list[str] = []
    current = header

    for item in items:
        line = "\n" + item
        # If adding this item would exceed the limit, start a new chunk
        if current and len(current) + len(line) > max_len:
            chunks.append(current)
            current = item
        else:
            current = current + line if current else item

    if current:
        chunks.append(current)

    return chunks
