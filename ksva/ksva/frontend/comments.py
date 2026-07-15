"""注释移除。对齐 spec 13.2。

删除 // 和 /* */ 注释，保留换行。
字符串中的 // 和 /* 不作为注释。
"""

from __future__ import annotations


def remove_comments_keep_lines(src: str) -> str:
    """删除 SVA 注释，保留换行以维持行号对应。

    规则：
    1. // 到行尾 → 替换为等量空格 + 换行
    2. / * ... * / → 替换为等量空格（保留内部换行）
    3. 字符串 "" 内的 // 和 /* 不视为注释
    """
    result: list[str] = []
    i = 0
    n = len(src)
    in_string = False

    while i < n:
        ch = src[i]

        # String literal
        if ch == '"' and (i == 0 or src[i - 1] != "\\"):
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if in_string:
            result.append(ch)
            i += 1
            continue

        # Line comment //
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            # Replace //... with spaces until newline
            while i < n and src[i] != "\n":
                result.append(" ")  # preserve column alignment
                i += 1
            continue

        # Block comment /* */
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2  # skip /*
            while i < n:
                if src[i] == "*" and i + 1 < n and src[i + 1] == "/":
                    i += 2  # skip */
                    break
                if src[i] == "\n":
                    result.append("\n")
                else:
                    result.append(" ")  # preserve column
                i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)
