"""Property 解析器 — SVA property/assertion 顶层入口。

递归下降解析：
1. property <name> → 捕获 name
2. @(posedge/negedge <signal>) → ClockIR
3. disable iff (<expr>) → disable_expr
4. 扫描 |-> / |=> token 位置 → implication 分界
5. |-> 之前 → antecedent_raw; |-> 之后 → consequent_raw
6. endproperty
"""

from __future__ import annotations

from ksva.ir.diagnostics import DiagnosticBag
from ksva.ir.surface import AssertionKind, ClockIR, LocalVarIR, SurfaceIR

from .scanner import Scanner, TokenKind


class PropertyParser:
    """解析 SVA property 和 assertion 声明。"""

    def __init__(self, scanner: Scanner, diag: DiagnosticBag) -> None:
        self._scanner = scanner
        self._diag = diag

    def parse_file(self) -> list[SurfaceIR]:
        """解析整个文件，返回所有 property/assertion 的 SurfaceIR 列表。"""
        results: list[SurfaceIR] = []
        while True:
            tk = self._scanner.peek()
            if tk.kind == TokenKind.EOF:
                break

            if tk.kind == TokenKind.KW_PROPERTY:
                ir = self.parse_property_declaration()
                if ir:
                    results.append(ir)
            elif tk.kind in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                ir = self.parse_assertion_statement()
                if ir:
                    results.append(ir)
            elif tk.kind == TokenKind.IDENT:
                saved = (self._scanner._pos, self._scanner._line, self._scanner._col)
                label_tk = self._scanner.advance()
                if (self._scanner.peek().kind == TokenKind.COLON):
                    self._scanner.advance()
                    if self._scanner.peek().kind in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                        ir = self.parse_assertion_statement(optional_label=label_tk.text)
                        if ir:
                            results.append(ir)
                        continue
                self._scanner._pos, self._scanner._line, self._scanner._col = saved
                self._scanner.advance()
            else:
                self._scanner.advance()
        return results

    def parse_property_declaration(self) -> SurfaceIR | None:
        """解析 property <name> ... endproperty。"""
        self._scanner.expect(TokenKind.KW_PROPERTY)

        # property name
        name_tk = self._scanner.expect(TokenKind.IDENT)
        name = name_tk.text

        # optional (...)
        # e.g. property p_name (signal sig);
        tk = self._scanner.peek()
        if tk.kind == TokenKind.LPAREN:
            self._scanner.advance()  # (
            formal_args: list[str] = []
            while self._scanner.peek().kind != TokenKind.RPAREN:
                arg_tk = self._scanner.advance()
                if arg_tk.kind != TokenKind.COMMA and arg_tk.kind != TokenKind.SEMICOLON:
                    if arg_tk.kind == TokenKind.KW_PROPERTY or arg_tk.kind == TokenKind.IDENT:
                        formal_args.append(arg_tk.text)
            self._scanner.advance()  # )
        # skip optional ;
        self._scanner.try_advance(TokenKind.SEMICOLON)

        # property-local variable declarations must come before clock/disable.
        # Keep this intentionally small: it covers the scalar/vector declarations
        # accepted by the MVP spec without trying to become a full SV parser.
        local_vars = self._parse_local_var_declarations()

        # 解析 clock 和 disable
        clock_info = self._parse_optional_clock_disable()

        # 解析 antecedent & consequent
        # 收集 implication 之前和之后的 raw text
        antecedent_tokens: list = []
        consequent_tokens: list = []
        saw_impl = False
        impl_kind = ""
        impl_found = self._scan_to_implication(antecedent_tokens)
        if impl_found:
            saw_impl = True
            impl_kind = impl_found
            consequent_tokens = self._collect_until_endproperty()

        # 重建 raw text
        antecedent_raw = self._reconstruct_raw(antecedent_tokens)
        consequent_raw = self._reconstruct_raw(consequent_tokens)

        # 如果没有 implication，整个 thing 就是 antecedent
        if not saw_impl:
            # 此时 antecedent_tokens 可能包含所有内容
            # 读取剩余到 endproperty
            rest = self._collect_until_endproperty()
            antecedent_tokens.extend(rest)
            antecedent_raw = self._reconstruct_raw(antecedent_tokens)
            consequent_raw = ""

        # 读取 endproperty
        self._scanner.try_advance(TokenKind.KW_ENDPROPERTY)
        self._scanner.try_advance(TokenKind.SEMICOLON)

        return SurfaceIR(
            schema_version="ksva.surface_ir.v1",
            name=name,
            kind=AssertionKind.PROPERTY.value,
            raw_text=antecedent_raw if not saw_impl else
                     f"{antecedent_raw} {impl_kind} {consequent_raw}",
            clock=clock_info,
            disable_expr=getattr(clock_info, 'disable_expr', ""),
            local_vars=local_vars,
            antecedent_raw=antecedent_raw,
            implication=impl_kind,
            consequent_raw=consequent_raw,
            is_named_property=True,
            is_inline_property=False,
        )

    def parse_assertion_statement(self, optional_label: str = "") -> SurfaceIR | None:
        """解析 assert/assume/cover property (...) 语句。"""
        kw_tk = self._scanner.advance()
        if kw_tk.kind == TokenKind.KW_ASSERT:
            kind = AssertionKind.ASSERT
        elif kw_tk.kind == TokenKind.KW_ASSUME:
            kind = AssertionKind.ASSUME
        else:
            kind = AssertionKind.COVER

        # 可选 label: name :
        label = optional_label
        tk = self._scanner.peek()
        if not label and tk.kind == TokenKind.IDENT:
            # look ahead for :
            saved = self._scanner.peek()
            self._scanner.advance()
            next_tk = self._scanner.peek()
            if next_tk.kind == TokenKind.COLON:
                label = saved.text
                self._scanner.advance()  # :
            # else it's not a label — we already consumed it, just proceed

        self._scanner.expect(TokenKind.KW_PROPERTY)

        # ( ... ) — inline property or named reference
        self._scanner.expect(TokenKind.LPAREN)

        name = ""
        antecedent_tokens: list = []
        consequent_tokens: list = []
        saw_impl = False
        impl_kind = ""

        tk = self._scanner.peek()
        if tk.kind == TokenKind.IDENT:
            # Could be a named property reference or inline
            # Look ahead
            name_tk = self._scanner.advance()
            name = name_tk.text
            next_tk = self._scanner.peek()
            if next_tk.kind == TokenKind.RPAREN:
                # Named reference: assert property (p_name);
                self._scanner.advance()  # )
                self._scanner.try_advance(TokenKind.SEMICOLON)
                return SurfaceIR(
                    schema_version="ksva.surface_ir.v1",
                    name=name,
                    label=label,
                    kind=kind.value,
                    is_named_property=False,
                    is_inline_property=True,
                    raw_text=f"{kind.value} property ({name})",
                )
            # else inline property — fall through
            antecedent_tokens.append(name_tk)
            name = ""

        # Parse inline property: look for implication
        # Collect tokens before )
        paren_depth = 1
        while paren_depth > 0:
            tk = self._scanner.peek()
            if tk.kind == TokenKind.EOF:
                break
            if tk.kind == TokenKind.LPAREN:
                paren_depth += 1
            elif tk.kind == TokenKind.RPAREN:
                paren_depth -= 1
                if paren_depth == 0:
                    self._scanner.advance()
                    break
            if tk.kind == TokenKind.IMPL_OVERLAPPED:
                saw_impl = True
                impl_kind = "|->"
                self._scanner.advance()  # consume but don't add to either side
                continue
            elif tk.kind == TokenKind.IMPL_NONOVERLAPPED:
                saw_impl = True
                impl_kind = "|=>"
                self._scanner.advance()  # consume but don't add to either side
                continue
            if not saw_impl:
                antecedent_tokens.append(self._scanner.advance())
            else:
                consequent_tokens.append(self._scanner.advance())

        self._scanner.try_advance(TokenKind.SEMICOLON)

        antecedent_raw = self._reconstruct_raw(antecedent_tokens)
        consequent_raw = self._reconstruct_raw(consequent_tokens)

        return SurfaceIR(
            schema_version="ksva.surface_ir.v1",
            name=name if name else f"__inline_{label}" if label else "__inline__",
            label=label,
            kind=kind.value,
            raw_text=f"{antecedent_raw} {impl_kind} {consequent_raw}".strip(),
            antecedent_raw=antecedent_raw,
            implication=impl_kind,
            consequent_raw=consequent_raw,
            is_named_property=False,
            is_inline_property=True,
        )

    def list_properties(self) -> list[dict]:
        """列出文件中所有 property/assertion（用于 ksva list 命令）。"""
        results: list[dict] = []
        saved_pos = (self._scanner._pos, self._scanner._line, self._scanner._col)

        while True:
            tk = self._scanner.peek()
            if tk.kind == TokenKind.EOF:
                break
            if tk.kind == TokenKind.KW_PROPERTY:
                self._scanner.advance()
                name_tk = self._scanner.peek()
                if name_tk.kind == TokenKind.IDENT:
                    self._scanner.advance()
                    results.append({"type": "property", "name": name_tk.text})
            elif tk.kind in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                kind = tk.kind.value
                self._scanner.advance()
                # check for label
                label = ""
                next_tk = self._scanner.peek()
                if next_tk.kind == TokenKind.IDENT:
                    self._scanner.advance()
                    colon_tk = self._scanner.peek()
                    if colon_tk.kind == TokenKind.COLON:
                        label = next_tk.text
                        self._scanner.advance()
                # skip to )
                self._scanner.advance()  # property
                self._scanner.advance()  # (
                skt = self._scanner.peek()
                if skt.kind == TokenKind.IDENT:
                    self._scanner.advance()
                    name = skt.text
                    rt = self._scanner.peek()
                    if rt.kind == TokenKind.RPAREN:
                        results.append({"type": kind, "name": name, "label": label})
                # skip rest
                while self._scanner.peek().kind not in (TokenKind.SEMICOLON, TokenKind.EOF):
                    self._scanner.advance()
                self._scanner.try_advance(TokenKind.SEMICOLON)
            elif tk.kind == TokenKind.IDENT:
                saved = (self._scanner._pos, self._scanner._line, self._scanner._col)
                label_tk = self._scanner.advance()
                if self._scanner.peek().kind == TokenKind.COLON:
                    self._scanner.advance()
                    if self._scanner.peek().kind in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                        kind_tk = self._scanner.advance()
                        kind = kind_tk.kind.value
                        label = label_tk.text
                        if self._scanner.peek().kind == TokenKind.KW_PROPERTY:
                            self._scanner.advance()
                            self._scanner.try_advance(TokenKind.LPAREN)
                            skt = self._scanner.peek()
                            if skt.kind == TokenKind.IDENT:
                                self._scanner.advance()
                                name = skt.text
                                if self._scanner.peek().kind == TokenKind.RPAREN:
                                    results.append({"type": kind, "name": name, "label": label})
                            while self._scanner.peek().kind not in (TokenKind.SEMICOLON, TokenKind.EOF):
                                self._scanner.advance()
                            self._scanner.try_advance(TokenKind.SEMICOLON)
                            continue
                self._scanner._pos, self._scanner._line, self._scanner._col = saved
                self._scanner.advance()
            else:
                self._scanner.advance()

        # restore position
        self._scanner._pos, self._scanner._line, self._scanner._col = saved_pos
        return results

    def scan_statistics(self) -> dict:
        """扫描文件，统计语法构造分布（用于 ksva scan 命令）。"""
        stats: dict = {
            "file": "",
            "property_blocks": 0,
            "inline_assertions": 0,
            "operators": {},
        }

        prev_kind = None
        while True:
            tk = self._scanner.peek()
            if tk.kind == TokenKind.EOF:
                break

            if tk.kind == TokenKind.KW_PROPERTY:
                if prev_kind not in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                    stats["property_blocks"] = stats.get("property_blocks", 0) + 1
            elif tk.kind in (TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER):
                stats["inline_assertions"] = stats.get("inline_assertions", 0) + 1

            # Count operators
            op_name = tk.kind.value
            if tk.kind in (TokenKind.IMPL_OVERLAPPED, TokenKind.IMPL_NONOVERLAPPED,
                           TokenKind.HASH_HASH, TokenKind.REPEAT_CONSEC,
                           TokenKind.REPEAT_NONCONSEC, TokenKind.REPEAT_GOTO,
                           TokenKind.KW_FIRST_MATCH, TokenKind.KW_THROUGHOUT,
                           TokenKind.KW_INTERSECT, TokenKind.KW_WITHIN,
                           TokenKind.SYS_PAST, TokenKind.SYS_ROSE, TokenKind.SYS_FELL,
                           TokenKind.SYS_STABLE, TokenKind.SYS_CHANGED):
                operators = stats.setdefault("operators", {})
                operators[op_name] = operators.get(op_name, 0) + 1

            prev_kind = self._scanner.advance().kind

        return stats

    # ── helpers ──

    def _parse_optional_clock_disable(self) -> ClockIR:
        """解析可选的 @(posedge clk) 和 disable iff (expr)。"""
        clock = ClockIR()

        # clock: @(posedge clk)
        tk = self._scanner.peek()
        if tk.kind == TokenKind.AT:
            self._scanner.advance()  # @
            self._scanner.expect(TokenKind.LPAREN)
            edge_tk = self._scanner.peek()
            edge = "unknown"
            if edge_tk.kind in (TokenKind.POSEDGE, TokenKind.NEGEDGE, TokenKind.EDGE):
                edge = edge_tk.kind.value
                self._scanner.advance()
            sig_tk = self._scanner.advance()
            signal = sig_tk.text
            self._scanner.expect(TokenKind.RPAREN)
            self._scanner.try_advance(TokenKind.SEMICOLON)
            clock = ClockIR(edge=edge, signal=signal, supported=True)

        # disable iff (expr)
        tk = self._scanner.peek()
        if tk.kind == TokenKind.KW_DISABLE:
            self._scanner.advance()
            self._scanner.expect(TokenKind.KW_IFF)
            self._scanner.expect(TokenKind.LPAREN)
            # 简单收集 disable expr 的 raw text
            disable_tokens: list = []
            depth = 1
            while depth > 0:
                dt = self._scanner.advance()
                if dt.kind == TokenKind.LPAREN:
                    depth += 1
                elif dt.kind == TokenKind.RPAREN:
                    depth -= 1
                    if depth == 0:
                        break
                disable_tokens.append(dt)
            self._scanner.try_advance(TokenKind.SEMICOLON)
            clock.disable_expr = self._reconstruct_raw(disable_tokens) if disable_tokens else ""

        return clock

    def _parse_local_var_declarations(self) -> list[LocalVarIR]:
        """解析 property body 开头的 local variable declaration。"""
        local_vars: list[LocalVarIR] = []
        type_keywords = {
            "logic", "reg", "bit", "int", "integer", "shortint", "longint",
            "byte", "time",
        }

        while True:
            first = self._scanner.peek()
            if first.kind != TokenKind.IDENT or first.text not in type_keywords:
                break

            decl_tokens = []
            while True:
                tk = self._scanner.peek()
                if tk.kind in (TokenKind.EOF, TokenKind.KW_ENDPROPERTY):
                    break
                tk = self._scanner.advance()
                if tk.kind == TokenKind.SEMICOLON:
                    break
                decl_tokens.append(tk)

            ident_tokens = [tk for tk in decl_tokens if tk.kind == TokenKind.IDENT]
            if len(ident_tokens) < 2:
                continue

            name = ident_tokens[-1].text
            name_idx = max(i for i, tk in enumerate(decl_tokens)
                           if tk.kind == TokenKind.IDENT and tk.text == name)
            var_type = self._reconstruct_raw(decl_tokens[:name_idx]).strip()
            local_vars.append(LocalVarIR(name=name, var_type=var_type))

        return local_vars

    def _scan_to_implication(self, antecedent_tokens: list) -> str | None:
        """收集 token 直到遇到 |-> 或 |=>，返回 implication 类型。

        如果直到 endproperty 都没遇到，返回 None。
        """
        while True:
            tk = self._scanner.peek()
            if tk.kind == TokenKind.EOF:
                return None
            if tk.kind == TokenKind.KW_ENDPROPERTY:
                return None
            if tk.kind == TokenKind.IMPL_OVERLAPPED:
                self._scanner.advance()  # consume |-> and DON'T add to antecedent
                return "|->"
            if tk.kind == TokenKind.IMPL_NONOVERLAPPED:
                self._scanner.advance()
                return "|=>"
            if tk.kind == TokenKind.SEMICOLON:
                # This might be the semicolon after clock/disable or end of property
                # Check if next is endproperty
                self._scanner.advance()
                antecedent_tokens.append(tk)
                if self._scanner.peek().kind == TokenKind.KW_ENDPROPERTY:
                    return None
                continue
            antecedent_tokens.append(self._scanner.advance())

    def _collect_until_endproperty(self) -> list:
        """收集 token 直到 endproperty。"""
        tokens: list = []
        while True:
            tk = self._scanner.peek()
            if tk.kind in (TokenKind.EOF, TokenKind.KW_ENDPROPERTY, TokenKind.KW_ENDSEQUENCE):
                break
            if tk.kind == TokenKind.SEMICOLON:
                self._scanner.advance()
                tokens.append(tk)
                if self._scanner.peek().kind == TokenKind.KW_ENDPROPERTY:
                    break
                continue
            tokens.append(self._scanner.advance())
        return tokens

    def _reconstruct_raw(self, tokens) -> str:
        """从 token 列表重建原始文本。"""
        if not tokens:
            return ""
        parts: list[str] = []
        for tk in tokens:
            parts.append(tk.text)
        return " ".join(parts)
