from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable


SENTENCE_END = re.compile(r"(?<=[.!?।؟!])\s+")


class ResponseSegmenter:
    def __init__(self, min_chars: int = 40) -> None:
        self.min_chars = min_chars
        self._buf = ""

    def push(self, token: str) -> list[str]:
        self._buf += token
        return self._flush(final=False)

    def finish(self) -> list[str]:
        return self._flush(final=True)

    def _flush(self, *, final: bool) -> list[str]:
        out: list[str] = []
        parts = SENTENCE_END.split(self._buf) if self._buf else []
        if not parts:
            if final and self._buf.strip():
                out.append(self._buf.strip())
                self._buf = ""
            return out
        if not final:
            hold = parts[-1]
            complete = parts[:-1]
        else:
            hold = ""
            complete = parts
        kept: list[str] = []
        acc = ""
        for piece in complete:
            acc = (acc + " " + piece).strip()
            if len(acc) >= self.min_chars:
                kept.append(acc)
                acc = ""
        if acc:
            if final:
                kept.append(acc)
            else:
                hold = acc + (" " + hold if hold else "")
        self._buf = hold
        return kept


async def iter_segments(chunks: Iterable[str] | AsyncIterator[str]) -> AsyncIterator[str]:
    seg = ResponseSegmenter()
    if hasattr(chunks, "__aiter__"):
        async for token in chunks:  # type: ignore[union-attr]
            for piece in seg.push(token):
                yield piece
    else:
        for token in chunks:  # type: ignore[union-attr]
            for piece in seg.push(token):
                yield piece
    for piece in seg.finish():
        yield piece
