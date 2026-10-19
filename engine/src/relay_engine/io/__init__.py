"""Storage adapters. The core only knows these two protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import polars as pl


class TableSource(Protocol):
    """Where tables are read from: local Parquet, or a sources catalog."""

    def read(self, table: str) -> pl.DataFrame: ...


class TableSink(Protocol):
    """Where a run writes its layers."""

    def write(self, frame: pl.DataFrame, path: str) -> None: ...


class LocalParquetStore:
    """Tables are `<root>/<table>.parquet`; outputs are Parquet directories under root."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def read(self, table: str) -> pl.DataFrame:
        return pl.read_parquet(self._root / f"{table}.parquet")

    def write(self, frame: pl.DataFrame, path: str) -> None:
        folder = self._root / path
        folder.mkdir(parents=True, exist_ok=False)
        frame.write_parquet(folder / "part-00000.parquet")
