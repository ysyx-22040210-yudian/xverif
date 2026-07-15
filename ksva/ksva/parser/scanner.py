"""手写 deterministic scanner for SVA.

|-> 和 |=> 作为整体 token（implication 分界关键）。
##、 [*、 [=、 [-> 作为整体 token。
$past/$rose/$fell/$stable/$changed/$isunknown 作为特殊标识符。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ksva.ir.common import SourceSpan


@enum.unique
class TokenKind(enum.Enum):
    EOF = "eof"
    IDENT = "ident"
    NUMBER = "number"

    # SVA keywords
    KW_PROPERTY = "property"
    KW_ENDPROPERTY = "endproperty"
    KW_ASSERT = "assert"
    KW_ASSUME = "assume"
    KW_COVER = "cover"
    KW_DISABLE = "disable"
    KW_IFF = "iff"
    KW_SEQUENCE = "sequence"
    KW_ENDSEQUENCE = "endsequence"
    KW_FIRST_MATCH = "first_match"
    KW_THROUGHOUT = "throughout"
    KW_INTERSECT = "intersect"
    KW_WITHIN = "within"
    KW_OR = "or"

    # System functions
    SYS_PAST = "$past"
    SYS_ROSE = "$rose"
    SYS_FELL = "$fell"
    SYS_STABLE = "$stable"
    SYS_CHANGED = "$changed"
    SYS_ISUNKNOWN = "$isunknown"
    SYS_ONEHOT = "$onehot"
    SYS_ONEHOT0 = "$onehot0"
    SYS_COUNTONES = "$countones"

    # Operators / delimiters
    IMPL_OVERLAPPED = "|->"  # overlapped implication
    IMPL_NONOVERLAPPED = "|=>"  # non-overlapped implication
    HASH_HASH = "##"  # cycle delay prefix
    LBRACKET = "["
    RBRACKET = "]"
    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    SEMICOLON = ";"
    COLON = ":"
    COMMA = ","
    DOLLAR = "$"
    AT = "@"
    STAR = "*"
    PLUS = "+"
    EQ = "="
    EQ_EQ = "=="
    NOT_EQ = "!="
    PIPE = "|"
    AMP = "&"
    CARET = "^"
    TILDE = "~"
    NOT = "!"
    LT = "<"
    GT = ">"
    DOT = "."
    HASH = "#"
    MINUS = "-"
    SLASH = "/"
    PERCENT = "%"
    QUESTION = "?"
    POSEDGE = "posedge"
    NEGEDGE = "negedge"
    EDGE = "edge"

    # Sequence repeat shortcuts – kept as raw chars, parser handles
    REPEAT_CONSEC = "[*"  # consecutive repeat
    REPEAT_NONCONSEC = "[="  # non-consecutive repeat
    REPEAT_GOTO = "[->"  # goto repeat


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    span: SourceSpan


# ── keyword / system function lookup ──

_KEYWORDS: dict[str, TokenKind] = {
    "property": TokenKind.KW_PROPERTY,
    "endproperty": TokenKind.KW_ENDPROPERTY,
    "assert": TokenKind.KW_ASSERT,
    "assume": TokenKind.KW_ASSUME,
    "cover": TokenKind.KW_COVER,
    "disable": TokenKind.KW_DISABLE,
    "iff": TokenKind.KW_IFF,
    "sequence": TokenKind.KW_SEQUENCE,
    "endsequence": TokenKind.KW_ENDSEQUENCE,
    "first_match": TokenKind.KW_FIRST_MATCH,
    "throughout": TokenKind.KW_THROUGHOUT,
    "intersect": TokenKind.KW_INTERSECT,
    "within": TokenKind.KW_WITHIN,
    "or": TokenKind.KW_OR,
    "posedge": TokenKind.POSEDGE,
    "negedge": TokenKind.NEGEDGE,
    "edge": TokenKind.EDGE,
}

_SYS_FUNCS: dict[str, TokenKind] = {
    "$past": TokenKind.SYS_PAST,
    "$rose": TokenKind.SYS_ROSE,
    "$fell": TokenKind.SYS_FELL,
    "$stable": TokenKind.SYS_STABLE,
    "$changed": TokenKind.SYS_CHANGED,
    "$isunknown": TokenKind.SYS_ISUNKNOWN,
    "$onehot": TokenKind.SYS_ONEHOT,
    "$onehot0": TokenKind.SYS_ONEHOT0,
    "$countones": TokenKind.SYS_COUNTONES,
}


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class Scanner:
    """SVA deterministic scanner."""

    def __init__(self, text: str, file: str = "<unknown>") -> None:
        self._text = text
        self._file = file
        self._pos = 0
        self._line = 1
        self._col = 1

    # ── helpers ──

    def _current(self) -> str:
        if self._pos < len(self._text):
            return self._text[self._pos]
        return "\0"

    def _advance(self) -> str:
        ch = self._current()
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _peek_next(self) -> str:
        if self._pos + 1 < len(self._text):
            return self._text[self._pos + 1]
        return "\0"

    def _skip_whitespace(self) -> None:
        while self._current() in (" ", "\t", "\n", "\r"):
            self._advance()

    def _skip_comments(self) -> None:
        """跳过 // 行注释和 /* */ 块注释。"""
        while True:
            self._skip_whitespace()
            if self._current() == "/" and self._peek_next() == "/":
                while self._current() not in ("\n", "\0"):
                    self._advance()
            elif self._current() == "/" and self._peek_next() == "*":
                self._advance()  # /
                self._advance()  # *
                while self._current() != "\0":
                    if self._current() == "*" and self._peek_next() == "/":
                        self._advance()
                        self._advance()
                        break
                    self._advance()
            else:
                break

    def _span_at(self, line: int, col: int) -> SourceSpan:
        return SourceSpan(file=self._file, begin_line=line, begin_col=col,
                          end_line=self._line, end_col=self._col)

    # ── token construction ──

    def _make_token(self, kind: TokenKind, text: str, start_line: int, start_col: int) -> Token:
        return Token(kind=kind, text=text, span=self._span_at(start_line, start_col))

    # ── scanning ──

    def _scan_ident_or_keyword(self) -> Token:
        start_line, start_col = self._line, self._col
        text = ""
        while _is_ident_part(self._current()):
            text += self._advance()

        # check system function
        raw = "$" + text
        if raw in _SYS_FUNCS:
            return self._make_token(_SYS_FUNCS[raw], raw, start_line, start_col)

        # check keyword
        if text in _KEYWORDS:
            return self._make_token(_KEYWORDS[text], text, start_line, start_col)

        return self._make_token(TokenKind.IDENT, text, start_line, start_col)

    def _scan_number(self) -> Token:
        start_line, start_col = self._line, self._col
        text = ""
        # hex prefix
        if self._current() == "'":
            text += self._advance()
            if self._current() in ("h", "H"):
                text += self._advance()
                while self._current().isdigit() or self._current().lower() in "abcdef":
                    text += self._advance()
            elif self._current() in ("d", "D", "b", "B", "o", "O"):
                text += self._advance()
                while self._current().isdigit():
                    text += self._advance()
            return self._make_token(TokenKind.NUMBER, text, start_line, start_col)

        while self._current().isdigit():
            text += self._advance()
        # 可选 'h 等
        if self._current() == "'":
            text += self._advance()
            if self._current() in ("h", "H", "d", "D", "b", "B", "o", "O"):
                text += self._advance()
            while self._current().isdigit() or self._current().lower() in "abcdef":
                text += self._advance()
        return self._make_token(TokenKind.NUMBER, text, start_line, start_col)

    def _scan_token(self) -> Token:
        self._skip_comments()
        start_line, start_col = self._line, self._col
        ch = self._current()

        if ch == "\0":
            return self._make_token(TokenKind.EOF, "", start_line, start_col)

        # $ 开头的系统函数或标识符
        if ch == "$":
            self._advance()
            text = ""
            while _is_ident_part(self._current()):
                text += self._advance()
            raw = "$" + text
            if raw in _SYS_FUNCS:
                return self._make_token(_SYS_FUNCS[raw], raw, start_line, start_col)
            return self._make_token(TokenKind.IDENT, raw, start_line, start_col)

        # 标识符
        if _is_ident_start(ch):
            return self._scan_ident_or_keyword()

        # 数字
        if ch.isdigit():
            return self._scan_number()

        # 多字符 token
        if ch == "|":
            self._advance()
            if self._current() == "-":
                self._advance()
                if self._current() == ">":
                    self._advance()
                    return self._make_token(TokenKind.IMPL_OVERLAPPED, "|->", start_line, start_col)
                return self._make_token(TokenKind.PIPE, "|", start_line, start_col)
            if self._current() == "=":
                self._advance()
                if self._current() == ">":
                    self._advance()
                    return self._make_token(TokenKind.IMPL_NONOVERLAPPED, "|=>", start_line, start_col)
                return self._make_token(TokenKind.PIPE, "|", start_line, start_col)
            return self._make_token(TokenKind.PIPE, "|", start_line, start_col)

        if ch == "#":
            self._advance()
            if self._current() == "#":
                self._advance()
                return self._make_token(TokenKind.HASH_HASH, "##", start_line, start_col)
            return self._make_token(TokenKind.HASH, "#", start_line, start_col)

        if ch == "[":
            self._advance()
            if self._current() == "*":
                self._advance()
                return self._make_token(TokenKind.REPEAT_CONSEC, "[*", start_line, start_col)
            if self._current() == "=":
                self._advance()
                return self._make_token(TokenKind.REPEAT_NONCONSEC, "[=", start_line, start_col)
            if self._current() == "-" and self._peek_next() == ">":
                self._advance()
                self._advance()
                return self._make_token(TokenKind.REPEAT_GOTO, "[->", start_line, start_col)
            return self._make_token(TokenKind.LBRACKET, "[", start_line, start_col)

        if ch == "=":
            self._advance()
            if self._current() == "=":
                self._advance()
                return self._make_token(TokenKind.EQ_EQ, "==", start_line, start_col)
            return self._make_token(TokenKind.EQ, "=", start_line, start_col)

        if ch == "!":
            self._advance()
            if self._current() == "=":
                self._advance()
                return self._make_token(TokenKind.NOT_EQ, "!=", start_line, start_col)
            return self._make_token(TokenKind.NOT, "!", start_line, start_col)

        # 单字符 token
        single_char: dict[str, TokenKind] = {
            "]": TokenKind.RBRACKET,
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            ";": TokenKind.SEMICOLON,
            ":": TokenKind.COLON,
            ",": TokenKind.COMMA,
            "@": TokenKind.AT,
            "*": TokenKind.STAR,
            "+": TokenKind.PLUS,
            "&": TokenKind.AMP,
            "^": TokenKind.CARET,
            "~": TokenKind.TILDE,
            "<": TokenKind.LT,
            ">": TokenKind.GT,
            ".": TokenKind.DOT,
            "-": TokenKind.MINUS,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
            "?": TokenKind.QUESTION,
        }
        if ch in single_char:
            self._advance()
            return self._make_token(single_char[ch], ch, start_line, start_col)

        # 未知字符 — 跳过
        self._advance()
        return self._make_token(TokenKind.IDENT, ch, start_line, start_col)

    # ── public API ──

    def peek(self) -> Token:
        """查看下一个 token，不消费。"""
        saved = (self._pos, self._line, self._col)
        token = self._scan_token()
        self._pos, self._line, self._col = saved
        return token

    def advance(self) -> Token:
        """消费并返回下一个 token。"""
        return self._scan_token()

    def expect(self, kind: TokenKind) -> Token:
        """消费下一个 token，必须是 kind，否则引发 ValueError。"""
        token = self.advance()
        if token.kind != kind:
            raise ValueError(f"expected {kind.value}, got {token.kind.value} ({token.text!r}) "
                             f"at {token.span.begin_line}:{token.span.begin_col}")
        return token

    def try_advance(self, kind: TokenKind) -> Token | None:
        """如果下一个 token 是 kind，消费并返回；否则返回 None。"""
        token = self.peek()
        if token.kind == kind:
            return self.advance()
        return None

    def __iter__(self):
        return self

    def __next__(self) -> Token:
        token = self.advance()
        if token.kind == TokenKind.EOF:
            raise StopIteration
        return token
