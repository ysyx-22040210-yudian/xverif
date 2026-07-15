"""Property/assertion 抽取器。对齐 spec 13.4-13.6。

从 SourceFile 中抽取 property block、assert/assume/cover statement，
建立 property symbol table。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ksva.ir.common import SourceSpan
from ksva.ir.surface import LocalVarIR


@dataclass
class PropertySymbol:
    """命名的 property block。对齐 spec 13.4。"""

    name: str
    body: str  # @(posedge clk) ... endproperty 内部的 sequence 部分
    local_vars: list[LocalVarIR] = field(default_factory=list)
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class AssertionSymbol:
    """assert/assume/cover 语句。对齐 spec 13.4。"""

    label: str = ""
    kind: str = "assert"  # assert / assume / cover
    is_ref: bool = False  # 引用已有 property 还是 inline
    property_ref: str = ""  # is_ref=True 时的 property name
    inline_body: str = ""  # is_ref=False 时的 inline body
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class SymbolTable:
    """Property/assertion 符号表。对齐 spec 13.4。"""

    properties: dict[str, PropertySymbol] = field(default_factory=dict)
    assertions: dict[str, AssertionSymbol] = field(default_factory=dict)
    inline_assertions: list[AssertionSymbol] = field(default_factory=list)


class Extractor:
    """从 SVA 源码抽取 property/assertion 符号。

    对齐 spec 13.5-13.6 的抽取规则。
    """

    def __init__(self, text: str, file: str = "<unknown>") -> None:
        self._text = text
        self._file = file
        self._unnamed_count = 0

    def extract(self) -> SymbolTable:
        """抽取所有 property 和 assertion，返回 SymbolTable。"""
        table = SymbolTable()

        text = self._text
        i = 0
        n = len(text)

        while i < n:
            # 跳过空白
            while i < n and text[i] in " \t\n\r":
                i += 1

            if i >= n:
                break

            # 跳过注释
            if text[i] == "/" and i + 1 < n:
                if text[i + 1] == "/":
                    while i < n and text[i] != "\n":
                        i += 1
                    continue
                if text[i + 1] == "*":
                    i += 2
                    while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                        i += 1
                    i += 2
                    continue

            # Check for property keyword
            keyword, keyword_len = self._match_keyword(text, i)
            if keyword is None:
                i += 1
                continue

            if keyword == "property":
                prop = self._extract_property(text, i)
                if prop:
                    table.properties[prop.name] = prop
                    i = self._find_end_property(text, i + keyword_len)
                else:
                    i += keyword_len
            elif keyword in ("assert", "assume", "cover"):
                assertion = self._extract_assertion(text, i, keyword)
                if assertion:
                    if assertion.is_ref:
                        table.assertions[assertion.label or assertion.property_ref] = assertion
                    else:
                        table.inline_assertions.append(assertion)
                    i = self._skip_to_semicolon_or_end(text, i)
                else:
                    i += keyword_len
            else:
                i += keyword_len

        return table

    def _match_keyword(self, text: str, pos: int) -> tuple[Optional[str], int]:
        """在 pos 位置尝试匹配关键字。返回 (keyword, length) 或 (None, 0)。"""
        keywords = ["property", "endproperty", "assert", "assume", "cover", "sequence"]

        for kw in keywords:
            end = pos + len(kw)
            if end <= len(text) and text[pos:end] == kw:
                # 确保是完整单词
                if end < len(text) and text[end].isalnum():
                    continue
                if text[end - 1] == kw[-1]:
                    return (kw, len(kw))

        # 检查 assert/assume/cover property
        for kw in ("assert", "assume", "cover"):
            rest = text[pos + len(kw):]
            if text[pos:pos + len(kw)] == kw and rest.strip().startswith("property"):
                return (kw, len(kw))

        return (None, 0)

    def _extract_property(self, text: str, pos: int) -> Optional[PropertySymbol]:
        """抽取 property <name> ... endproperty。"""
        # 跳过 "property"
        j = pos + len("property")
        # 跳过空白
        while j < len(text) and text[j] in " \t":
            j += 1

        if j >= len(text):
            return None

        # 读取 name（可能是标识符或括号参数列表）
        name = ""
        if text[j] == "(":
            # property p_name (signal sig);
            depth = 1
            j += 1
            paren_start = j
            while j < len(text) and depth > 0:
                if text[j] == "(": depth += 1
                elif text[j] == ")": depth -= 1
                j += 1
            # Next is name
            while j < len(text) and text[j] in " \t":
                j += 1
            name_start = j
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            name = text[name_start:j]
        else:
            name_start = j
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            name = text[name_start:j]

        # 跳过可选分号
        while j < len(text) and text[j] in " \t;\n\r":
            j += 1

        # 找到 ";"
        semi = text.find(";", j) if j < len(text) else -1
        if semi >= 0 and "endproperty" not in text[j:semi].lower():
            # 跳过 clock/disable 前的分号
            j = semi + 1

        # body 到 endproperty
        end_pos = text.find("endproperty", j)
        if end_pos < 0:
            return None

        body = text[j:end_pos].strip()

        # 去掉末尾分号
        body = body.rstrip(";").strip()

        return PropertySymbol(name=name, body=body)

    def _extract_assertion(self, text: str, pos: int, kind: str) -> Optional[AssertionSymbol]:
        """抽取 <label>: assert/assume/cover property (...) 。"""
        j = pos
        label = ""

        # 读 label（可选）：ident :
        saved_j = j
        while j < len(text) and text[j] != ":" and not text[j].isspace():
            j += 1
        if j < len(text) and text[j] == ":":
            label = text[saved_j:j].strip()
            j += 1  # skip :

        # 跳过到 "property ("
        rest = text[j:]
        prop_idx = rest.find("property")
        if prop_idx < 0:
            return None
        j += prop_idx + len("property")

        # 找到 (
        paren_start = text.find("(", j)
        if paren_start < 0:
            return None

        paren_end = self._find_matching_paren(text, paren_start)
        if paren_end < 0:
            return None

        inner = text[paren_start + 1:paren_end].strip()

        # Distinguish: named ref vs inline
        # Named ref: just an identifier
        is_ref = self._is_plain_identifier(inner)
        if is_ref:
            return AssertionSymbol(
                label=label, kind=kind, is_ref=True,
                property_ref=inner,
            )
        else:
            name = f"unnamed_{kind}_{self._unnamed_count}__"
            self._unnamed_count += 1
            return AssertionSymbol(
                label=label, kind=kind, is_ref=False,
                inline_body=inner,
            )

    def _find_matching_paren(self, text: str, pos: int) -> int:
        """找到与 pos 处 ( 匹配的 ) 位置。"""
        if pos >= len(text) or text[pos] != "(":
            return -1
        depth = 1
        i = pos + 1
        while i < len(text) and depth > 0:
            if text[i] == "(": depth += 1
            elif text[i] == ")": depth -= 1
            i += 1
        return i - 1 if depth == 0 else -1

    def _is_plain_identifier(self, s: str) -> bool:
        """判断字符串是否是纯粹的标识符（不含运算符、空格等）。"""
        return s.isidentifier()

    def _find_end_property(self, text: str, pos: int) -> int:
        ep = text.find("endproperty", pos)
        return ep + len("endproperty") if ep >= 0 else pos

    def _skip_to_semicolon_or_end(self, text: str, pos: int) -> int:
        semi = text.find(";", pos)
        return semi + 1 if semi >= 0 else pos
