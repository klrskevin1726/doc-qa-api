def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1.")

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start > start and not text[next_start].isspace():
            next_start -= 1
        if next_start <= start:
            next_start = end
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks