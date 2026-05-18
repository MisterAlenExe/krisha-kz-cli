from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

import orjson
from pydantic import BaseModel


@contextmanager
def open_output(path: str | None) -> Iterator[IO[bytes]]:
    """`None` or `"-"` => stdout; otherwise open file binary."""
    if path is None or path == "-":
        yield sys.stdout.buffer
        return
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    f = p.open("wb")
    try:
        yield f
    finally:
        f.close()


def write_jsonl(stream: IO[bytes], record: BaseModel | dict) -> None:
    if isinstance(record, BaseModel):
        payload = record.model_dump(mode="json")
    else:
        payload = record
    stream.write(orjson.dumps(payload))
    stream.write(b"\n")
    stream.flush()
