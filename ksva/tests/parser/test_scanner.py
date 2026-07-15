"""Scanner 单元测试。"""

from ksva.parser.scanner import Scanner, TokenKind


def test_empty_input():
    scanner = Scanner("")
    assert scanner.advance().kind == TokenKind.EOF


def test_keywords():
    scanner = Scanner("property endproperty assert assume cover disable iff "
                      "first_match throughout intersect within or sequence endsequence")
    expected = [
        TokenKind.KW_PROPERTY, TokenKind.KW_ENDPROPERTY,
        TokenKind.KW_ASSERT, TokenKind.KW_ASSUME, TokenKind.KW_COVER,
        TokenKind.KW_DISABLE, TokenKind.KW_IFF,
        TokenKind.KW_FIRST_MATCH, TokenKind.KW_THROUGHOUT,
        TokenKind.KW_INTERSECT, TokenKind.KW_WITHIN, TokenKind.KW_OR,
        TokenKind.KW_SEQUENCE, TokenKind.KW_ENDSEQUENCE,
    ]
    for exp in expected:
        token = scanner.advance()
        assert token.kind == exp, f"Expected {exp}, got {token.kind}"


def test_implication_tokens():
    scanner = Scanner("|-> |=>")
    t1 = scanner.advance()
    assert t1.kind == TokenKind.IMPL_OVERLAPPED
    assert t1.text == "|->"
    t2 = scanner.advance()
    assert t2.kind == TokenKind.IMPL_NONOVERLAPPED
    assert t2.text == "|=>"


def test_delay_tokens():
    scanner = Scanner("## ##[1:4] ##[3:$]")
    t = scanner.advance()
    assert t.kind == TokenKind.HASH_HASH
    t = scanner.advance()
    assert t.kind == TokenKind.HASH_HASH


def test_repeat_shortcuts():
    scanner = Scanner("[* [= [->")
    t = scanner.advance()
    assert t.kind == TokenKind.REPEAT_CONSEC
    t = scanner.advance()
    assert t.kind == TokenKind.REPEAT_NONCONSEC
    t = scanner.advance()
    assert t.kind == TokenKind.REPEAT_GOTO


def test_system_functions():
    scanner = Scanner("$past $rose $fell $stable $changed $isunknown")
    expected = [
        TokenKind.SYS_PAST, TokenKind.SYS_ROSE, TokenKind.SYS_FELL,
        TokenKind.SYS_STABLE, TokenKind.SYS_CHANGED, TokenKind.SYS_ISUNKNOWN,
    ]
    for exp in expected:
        token = scanner.advance()
        assert token.kind == exp, f"Expected {exp}, got {token.kind} for text {token.text}"


def test_line_comments():
    scanner = Scanner("// comment line\nreq")
    token = scanner.advance()
    assert token.kind == TokenKind.IDENT
    assert token.text == "req"


def test_block_comments():
    scanner = Scanner("/* block \n comment */ req")
    token = scanner.advance()
    assert token.kind == TokenKind.IDENT
    assert token.text == "req"


def test_posedge_negedge():
    scanner = Scanner("posedge negedge edge")
    t = scanner.advance()
    assert t.kind == TokenKind.POSEDGE
    t = scanner.advance()
    assert t.kind == TokenKind.NEGEDGE
    t = scanner.advance()
    assert t.kind == TokenKind.EDGE


def test_peek_and_advance():
    scanner = Scanner("a b")
    t1 = scanner.peek()
    t2 = scanner.peek()  # should be same
    assert t1.text == t2.text
    t3 = scanner.advance()
    assert t1.text == t3.text
    t4 = scanner.advance()
    assert t4.text == "b"


def test_comparison_operators():
    scanner = Scanner("== !=")
    t = scanner.advance()
    assert t.kind == TokenKind.EQ_EQ
    t = scanner.advance()
    assert t.kind == TokenKind.NOT_EQ


def test_full_property_scan():
    sva = """
property p_req_ack;
  @(posedge clk) disable iff (!rst_n)
  req |-> ##[1:4] ack;
endproperty
"""
    scanner = Scanner(sva)
    tokens = list(scanner)
    kinds = [t.kind for t in tokens]
    assert TokenKind.KW_PROPERTY in kinds
    assert TokenKind.IMPL_OVERLAPPED in kinds
    assert TokenKind.HASH_HASH in kinds
    assert TokenKind.KW_ENDPROPERTY in kinds
