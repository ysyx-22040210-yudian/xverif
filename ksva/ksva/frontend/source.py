"""源码文件读取与位置映射。对齐 spec 13.1。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SourceFile:
    """Source file with path, text, and offset-to-line/col mapping."""

    path: str
    text: str

    def line_col(self, offset: int) -> tuple[int, int]:
        """返回 offset 位置的 (line, col)，1-based。"""
        if offset < 0 or offset > len(self.text):
            return (0, 0)
        line = 1
        col = 1
        for i, ch in enumerate(self.text):
            if i >= offset:
                break
            if ch == "\n":
                line += 1
                col = 1
            else:
                col += 1
        return (line, col)

    @classmethod
    def from_file(cls, filepath: str) -> "SourceFile":
        """从文件路径读取。"""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"file not found: {filepath}")
        return cls(path=str(path.resolve()), text=path.read_text(encoding="utf-8"))
