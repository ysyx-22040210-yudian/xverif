"""Sequence parser 工具函数。对齐 spec 15.2。

所有函数在识别分隔符/关键字时维护 paren/bracket/brace/string 深度，
只在 depth 为 0（顶层）时识别。
"""

from __future__ import annotations


def split_top_level(s: str, sep: str) -> list[str]:
    """在顶层按 sep 分割字符串。不拆分嵌套在 () / [] / {} 内的 sep。"""
    parts: list[str] = []
    current: list[str] = []
    depth = _DepthTracker()
    i = 0
    sep_len = len(sep)

    while i < len(s):
        depth.feed(s[i])

        if depth.is_top_level and s[i:i + sep_len] == sep:
            parts.append("".join(current).strip())
            current = []
            i += sep_len
            continue

        current.append(s[i])
        i += 1

    parts.append("".join(current).strip())
    return [p for p in parts if p]  # 过滤空白


def find_top_level_keyword(s: str, keywords: list[str]) -> tuple[int, str] | None:
    """在字符串中找到第一个在顶层出现的关键字。

    返回 (position, keyword) 或 None。
    """
    depth = _DepthTracker()

    for i, ch in enumerate(s):
        depth.feed(ch)

        if not depth.is_top_level:
            continue

        for kw in keywords:
            if s[i:i + len(kw)] == kw:
                # 确保是完整单词
                end = i + len(kw)
                if end < len(s) and (s[end].isalnum() or s[end] == "_"):
                    continue
                return (i, kw)

    return None


def strip_outer_parens(s: str) -> str:
    """如果字符串最外层是一对匹配的 ()，则去掉。"""
    s = s.strip()
    if s.startswith("(") and s.endswith(")") and has_balanced_outer_parens(s):
        return s[1:-1].strip()
    return s


def has_balanced_outer_parens(s: str) -> bool:
    """检查字符串最外层的括号是否平衡。"""
    s = s.strip()
    if not s.startswith("(") or not s.endswith(")"):
        return False

    depth = 0
    for i, ch in enumerate(s):
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        # depth 在最后一个字符之前归零 → 不平衡
        if i < len(s) - 1 and depth == 0:
            return False
    return depth == 0


class _DepthTracker:
    """括号/字符串深度跟踪器。"""

    def __init__(self) -> None:
        self.paren_depth = 0
        self.bracket_depth = 0
        self.brace_depth = 0
        self.in_string = False
        self._prev_char = ""

    def feed(self, ch: str) -> None:
        if self.in_string:
            if ch == '"' and self._prev_char != "\\":
                self.in_string = False
        else:
            if ch == '"':
                self.in_string = True
            elif ch == "(":
                self.paren_depth += 1
            elif ch == ")":
                if self.paren_depth > 0:
                    self.paren_depth -= 1
            elif ch == "[":
                self.bracket_depth += 1
            elif ch == "]":
                if self.bracket_depth > 0:
                    self.bracket_depth -= 1
            elif ch == "{":
                self.brace_depth += 1
            elif ch == "}":
                if self.brace_depth > 0:
                    self.brace_depth -= 1
        self._prev_char = ch

    @property
    def is_top_level(self) -> bool:
        return (self.paren_depth == 0 and self.bracket_depth == 0
                and self.brace_depth == 0 and not self.in_string)
