"""
MINI COMPILER: Lexer → Parser → AST → Code Generator
For StickFrame .sf script DSL
"""

import re, json
from dataclasses import dataclass, field
from enum import Enum

# ============================================================ #
# 1. LEXER
# ============================================================ #

class TokenType(Enum):
    SCENE = 'SCENE'; CHARACTER = 'CHARACTER'; CAMERA = 'CAMERA'
    TIMELINE = 'TIMELINE'; RIG = 'RIG'; APPEARANCE = 'APPEARANCE'
    POSITION = 'POSITION'; FOLLOW = 'FOLLOW'; ZOOM = 'ZOOM'
    IDENTIFIER = 'IDENTIFIER'; NUMBER = 'NUMBER'; STRING = 'STRING'
    COLON = 'COLON'; COMMA = 'COMMA'; DOT = 'DOT'; EQUALS = 'EQUALS'
    LPAREN = 'LPAREN'; RPAREN = 'RPAREN'; LBRACE = 'LBRACE'; RBRACE = 'RBRACE'
    NEWLINE = 'NEWLINE'; INDENT = 'INDENT'; DEDENT = 'DEDENT'
    COMMENT = 'COMMENT'; EOF = 'EOF'; ACTION = 'ACTION'
    # Scripting language tokens
    SCRIPT = 'SCRIPT'; VAR = 'VAR'; REPEAT = 'REPEAT'; FOR = 'FOR'
    IF = 'IF'; ELSE = 'ELSE'; DEF = 'DEF'; RETURN = 'RETURN'
    IN = 'IN'; AT = 'AT'; OP = 'OP'; AND = 'AND'; OR = 'OR'; NOT = 'NOT'

@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int

KEYWORDS = {
    'scene': TokenType.SCENE, 'character': TokenType.CHARACTER,
    'camera': TokenType.CAMERA, 'timeline': TokenType.TIMELINE,
    'rig': TokenType.RIG, 'appearance': TokenType.APPEARANCE,
    'position': TokenType.POSITION, 'follow': TokenType.FOLLOW,
    'zoom': TokenType.ZOOM, 'action': TokenType.ACTION,
    # scripting keywords
    'script': TokenType.SCRIPT, 'var': TokenType.VAR,
    'repeat': TokenType.REPEAT, 'for': TokenType.FOR,
    'if': TokenType.IF, 'else': TokenType.ELSE,
    'def': TokenType.DEF, 'return': TokenType.RETURN,
    'in': TokenType.IN, 'at': TokenType.AT,
    'and': TokenType.AND, 'or': TokenType.OR, 'not': TokenType.NOT,
}

class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.indent_stack = [0]

    def peek(self, offset=0):
        idx = self.pos + offset
        return self.text[idx] if idx < len(self.text) else '\0'

    def advance(self):
        ch = self.text[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_whitespace(self):
        while self.pos < len(self.text) and self.peek() in ' \t\r':
            self.advance()

    def count_indent(self):
        """Count leading spaces without consuming them"""
        count = 0
        idx = self.pos
        while idx < len(self.text) and self.text[idx] == ' ':
            count += 1
            idx += 1
        while idx < len(self.text) and self.text[idx] == '\t':
            count += 4
            idx += 1
        return count

    def _prev_allows_unary(self) -> bool:
        """True if a '-' at the current point should be a NEGATIVE literal
        (start of file, after operator / '=' / '(' / ',' / keyword) rather
        than a subtraction operator."""
        if not self.tokens:
            return True
        t = self.tokens[-1]
        return t.type in (TokenType.OP, TokenType.EQUALS, TokenType.LPAREN,
                          TokenType.RETURN, TokenType.IF, TokenType.VAR,
                          TokenType.COMMA, TokenType.REPEAT, TokenType.AT,
                          TokenType.AND, TokenType.OR, TokenType.NOT)

    def read_number(self):
        start = self.pos
        # Handle leading minus
        if self.peek() == '-':
            self.advance()
        while self.pos < len(self.text) and (self.peek().isdigit() or self.peek() == '.'):
            self.advance()
        return self.text[start:self.pos]

    def read_identifier(self):
        start = self.pos
        while self.pos < len(self.text) and (self.peek().isalnum() or self.peek() == '_'):
            self.advance()
        return self.text[start:self.pos]

    def read_string(self):
        self.advance()
        start = self.pos
        while self.pos < len(self.text) and self.peek() != '"':
            self.advance()
        val = self.text[start:self.pos]
        self.advance()
        return val

    def handle_indent(self):
        spaces = 0
        while self.peek() == ' ':
            spaces += 1
            self.advance()
        if spaces > self.indent_stack[-1]:
            self.indent_stack.append(spaces)
            self.tokens.append(Token(TokenType.INDENT, 'indent', self.line, self.col))
        elif spaces < self.indent_stack[-1]:
            while spaces < self.indent_stack[-1]:
                self.indent_stack.pop()
                self.tokens.append(Token(TokenType.DEDENT, 'dedent', self.line, self.col))

    def tokenize(self):
        while self.pos < len(self.text):
            ch = self.peek()
            if ch == '\n':
                self.advance()
                self.tokens.append(Token(TokenType.NEWLINE, '\\n', self.line - 1, 1))
                # Count indentation of the next line
                if self.pos < len(self.text):
                    indent_level = self.count_indent()
                    # Skip over these whitespace chars now
                    self.skip_whitespace()
                    # Skip blank lines (don't change indent)
                    while self.pos < len(self.text) and self.peek() == '\n':
                        self.advance()
                        self.tokens.append(Token(TokenType.NEWLINE, '\\n', self.line - 1, 1))
                        indent_level = self.count_indent()
                        self.skip_whitespace()
                    if self.pos >= len(self.text) or self.peek() == '#':
                        # Comment-only or empty line after blank lines - reset indent tracking
                        continue
                    while indent_level > self.indent_stack[-1]:
                        self.indent_stack.append(indent_level)
                        self.tokens.append(Token(TokenType.INDENT, 'indent', self.line, self.col))
                    while indent_level < self.indent_stack[-1]:
                        self.indent_stack.pop()
                        self.tokens.append(Token(TokenType.DEDENT, 'dedent', self.line, self.col))
                continue
            if ch in ' \t':
                self.advance()
                continue
            if ch == '#':
                while self.pos < len(self.text) and self.peek() != '\n':
                    self.advance()
                continue
            if ch == '"':
                line, col = self.line, self.col
                val = self.read_string()
                self.tokens.append(Token(TokenType.STRING, val, line, col))
                continue
            if ch.isdigit():
                line, col = self.line, self.col
                val = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, val, line, col))
                continue
            if ch == '-' and self.pos + 1 < len(self.text) and \
                    (self.text[self.pos + 1].isdigit() or self.text[self.pos + 1] == '.') and \
                    self._prev_allows_unary():
                line, col = self.line, self.col
                val = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, val, line, col))
                continue
            if ch.isalpha() or ch == '_':
                line, col = self.line, self.col
                word = self.read_identifier()
                tok_type = KEYWORDS.get(word, TokenType.IDENTIFIER)
                self.tokens.append(Token(tok_type, word, line, col))
                continue
            # two-char comparison / equality operators
            if ch in ('=', '!', '<', '>') and self.peek(1) == '=':
                line, col = self.line, self.col
                self.advance(); self.advance()
                self.tokens.append(Token(TokenType.OP, ch + '=', line, col))
                continue
            # single-char arithmetic / comparison operators
            if ch in '+-*/%<>':
                line, col = self.line, self.col
                self.advance()
                self.tokens.append(Token(TokenType.OP, ch, line, col))
                continue
            single_map = {
                ':': TokenType.COLON, ',': TokenType.COMMA, '.': TokenType.DOT,
                '=': TokenType.EQUALS, '(': TokenType.LPAREN, ')': TokenType.RPAREN,
                '{': TokenType.LBRACE, '}': TokenType.RBRACE,
            }
            if ch in single_map:
                tt = single_map[ch]
                self.tokens.append(Token(tt, ch, self.line, self.col))
                self.advance()
                continue
            self.advance()

        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, 'dedent', self.line, self.col))
        self.tokens.append(Token(TokenType.EOF, 'EOF', self.line, self.col))
        return self.tokens


# ============================================================ #
# 2. PARSER
# ============================================================ #

@dataclass
class SceneDef:
    name: str; width: int; height: int; fps: int

@dataclass
class CharacterDef:
    name: str; rig: str; appearance: dict; position: tuple; scale: float = 1.0

@dataclass
class CameraDef:
    name: str; follow: str; zoom: float

@dataclass
class ActionDef:
    name: str; duration: float; loop: bool = False; keyframes: list = field(default_factory=list)
    # keyframes = [(time, {bone: angle_in_degrees}), ...]

@dataclass
class TimelineEvent:
    time: float; action: str; params: dict

@dataclass
class Timeline:
    scenes: dict

@dataclass
class Script:
    scenes: list; characters: list; cameras: list; timeline: Timeline
    actions: list = field(default_factory=list)
    script: list = field(default_factory=list)  # scripted statements (interpreted)


# ─── Scripting statement / expression nodes ──────────────────────
@dataclass
class SAssign:
    name: str; op: str; value: "SEXPR"

@dataclass
class SSchedule:
    entity: str; action: str; params: dict; time: "SEXPR"

@dataclass
class SRepeat:
    count: "SEXPR"; body: list

@dataclass
class SFor:
    var: str; iter_expr: "SEXPR"; body: list

@dataclass
class SIf:
    cond: "SEXPR"; body: list; else_body: list

@dataclass
class SDef:
    name: str; params: list; body: list

@dataclass
class SReturn:
    value: "SEXPR"

@dataclass
class SExpr:
    expr: object  # bare expression statement e.g. function call, result ignored


# ─── Expressions ─────────────────────────────────────────────────
@dataclass
class ENumber:
    value: float

@dataclass
class EString:
    value: str

@dataclass
class EVar:
    name: str

@dataclass
class EBin:
    op: str; left: object; right: object

@dataclass
class EUnary:
    op: str; operand: object

@dataclass
class ECall:
    name: str; args: list

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset=0):
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, *types):
        tok = self.peek()
        if tok and tok.type in types:
            return self.advance()
        got = tok.value if tok else 'EOF'
        expected = ', '.join(t.value for t in types)
        raise SyntaxError(f"Line {tok.line if tok else '?'}: Expected {expected}, got '{got}'")

    def skip_newlines(self):
        while self.peek() and self.peek().type == TokenType.NEWLINE:
            self.advance()

    def parse(self):
        script = Script(scenes=[], characters=[], cameras=[], timeline=None)
        self.skip_newlines()
        while self.peek() and self.peek().type != TokenType.EOF:
            tok = self.peek()
            if tok.type == TokenType.SCENE:
                script.scenes.append(self.parse_scene_def())
            elif tok.type == TokenType.CHARACTER:
                script.characters.append(self.parse_character_def())
            elif tok.type == TokenType.CAMERA:
                script.cameras.append(self.parse_camera_def())
            elif tok.type == TokenType.TIMELINE:
                script.timeline = self.parse_timeline()
            elif tok.type == TokenType.ACTION:
                script.actions.append(self.parse_action_def())
            elif tok.type == TokenType.SCRIPT:
                script.script = self.parse_script()
            else:
                self.advance()
            self.skip_newlines()
        return script

    # ── Scripted block (creative programming layer) ───────────────
    def parse_script(self):
        """Parse a `script:` block into a list of statements."""
        self.expect(TokenType.SCRIPT)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        return self.parse_script_block()

    def parse_script_block(self) -> list:
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        stmts = []
        while True:
            self.skip_newlines()
            t = self.peek()
            if t is None or t.type in (TokenType.DEDENT, TokenType.EOF):
                break
            stmts.append(self.parse_statement())
            # consume the trailing newline after a statement (if any)
            if self.peek() and self.peek().type == TokenType.NEWLINE:
                self.advance()
        if self.peek() and self.peek().type == TokenType.DEDENT:
            self.advance()
        return stmts

    def parse_statement(self):
        tok = self.peek()
        tt = tok.type if tok else None

        if tt == TokenType.VAR:            # var x = expr
            self.advance()
            name = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.EQUALS)
            return SAssign(name, '=', self.parse_expression())

        if tt == TokenType.REPEAT:         # repeat expr : block
            self.advance()
            n = self.parse_expression()
            if self.peek() and self.peek().type == TokenType.IDENTIFIER \
                    and self.peek().value == 'times':
                self.advance()
            self.expect(TokenType.COLON)
            return SRepeat(n, self.parse_script_block())

        if tt == TokenType.FOR:            # for i in expr : block
            self.advance()
            name = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.IN)
            it = self.parse_expression()
            self.expect(TokenType.COLON)
            return SFor(name, it, self.parse_script_block())

        if tt == TokenType.IF:             # if expr : block [else : block]
            self.advance()
            cond = self.parse_expression()
            self.expect(TokenType.COLON)
            body = self.parse_script_block()
            else_body = []
            if self.peek() and self.peek().type == TokenType.ELSE:
                self.advance()
                self.expect(TokenType.COLON)
                else_body = self.parse_script_block()
            return SIf(cond, body, else_body)

        if tt == TokenType.DEF:            # def name(a, b) : block
            self.advance()
            name = self.expect(TokenType.IDENTIFIER).value
            params = []
            if self.peek() and self.peek().type == TokenType.LPAREN:
                self.advance()
                while self.peek() and self.peek().type != TokenType.RPAREN:
                    params.append(self.expect(TokenType.IDENTIFIER).value)
                    if self.peek() and self.peek().type == TokenType.COMMA:
                        self.advance()
                self.expect(TokenType.RPAREN)
            self.expect(TokenType.COLON)
            return SDef(name, params, self.parse_script_block())

        if tt == TokenType.RETURN:        # return expr
            self.advance()
            return SReturn(self.parse_expression())

        if tt == TokenType.IDENTIFIER:
            first = tok.value
            self.advance()
            nxt = self.peek()
            if nxt and nxt.type == TokenType.DOT:
                # schedule: entity.action(params) at expr
                self.advance()
                action = self.advance().value
                params = {}
                if self.peek() and self.peek().type == TokenType.LPAREN:
                    self.advance()
                    while self.peek() and self.peek().type != TokenType.RPAREN:
                        key = self.advance().value  # any token; use its value
                        self.expect(TokenType.EQUALS)
                        params[key] = self.parse_expression()
                        if self.peek() and self.peek().type == TokenType.COMMA:
                            self.advance()
                    self.expect(TokenType.RPAREN)
                self.expect(TokenType.AT)
                return SSchedule(first, action, params, self.parse_expression())
            if nxt and nxt.type == TokenType.LPAREN:
                # bare call expression statement, e.g. combo(2) or print(x)
                self.advance()  # (
                args = []
                while self.peek() and self.peek().type != TokenType.RPAREN:
                    args.append(self.parse_expression())
                    if self.peek() and self.peek().type == TokenType.COMMA:
                        self.advance()
                self.expect(TokenType.RPAREN)
                return SExpr(ECall(first, args))
            if nxt and nxt.type == TokenType.EQUALS:
                self.advance()  # =
                return SAssign(first, '=', self.parse_expression())
            if nxt and nxt.type == TokenType.OP and nxt.value in '+-*/%' and \
                    self.peek(1) and self.peek(1).type == TokenType.EQUALS:
                op = self.advance().value  # OP
                self.advance()            # EQUALS
                return SAssign(first, op + '=', self.parse_expression())
            raise SyntaxError(
                f"Line {tok.line}: unexpected expression statement starting with '{first}'")

        raise SyntaxError(
            f"Line {tok.line if tok else '?'}: unexpected token '{tok.value}' "
            f"in script block")

    # ── Expressions (precedence climbing) ──────────────────────────
    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.peek() and self.peek().type == TokenType.OR:
            self.advance()
            left = EBin('or', left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.peek() and self.peek().type == TokenType.AND:
            self.advance()
            left = EBin('and', left, self.parse_not())
        return left

    def parse_not(self):
        if self.peek() and self.peek().type == TokenType.NOT:
            self.advance()
            return EUnary('not', self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_add()
        while self.peek() and self.peek().type == TokenType.OP and \
                self.peek().value in ('<', '>', '==', '!=', '<=', '>='):
            op = self.advance().value
            left = EBin(op, left, self.parse_add())
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.peek() and self.peek().type == TokenType.OP and \
                self.peek().value in ('+', '-'):
            op = self.advance().value
            left = EBin(op, left, self.parse_mul())
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.peek() and self.peek().type == TokenType.OP and \
                self.peek().value in ('*', '/', '%'):
            op = self.advance().value
            left = EBin(op, left, self.parse_unary())
        return left

    def parse_unary(self):
        if self.peek() and self.peek().type == TokenType.OP and \
                self.peek().value in ('+', '-'):
            op = self.advance().value
            return EUnary(op, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        tok = self.peek()
        if tok is None:
            raise SyntaxError("Unexpected end of script while parsing expression")
        if tok.type == TokenType.NUMBER:
            self.advance()
            return ENumber(float(tok.value))
        if tok.type == TokenType.STRING:
            self.advance()
            return EString(str(tok.value))
        if tok.type == TokenType.LPAREN:
            self.advance()
            e = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return e
        if tok.type == TokenType.IDENTIFIER:
            self.advance()
            if self.peek() and self.peek().type == TokenType.LPAREN:
                self.advance()
                args = []
                while self.peek() and self.peek().type != TokenType.RPAREN:
                    args.append(self.parse_expression())
                    if self.peek() and self.peek().type == TokenType.COMMA:
                        self.advance()
                self.expect(TokenType.RPAREN)
                return ECall(tok.value, args)
            return EVar(tok.value)
        raise SyntaxError(
            f"Line {tok.line}: unexpected token '{tok.value}' in expression")

    def parse_scene_def(self):
        self.expect(TokenType.SCENE)
        name = self.expect(TokenType.IDENTIFIER).value
        width, height, fps = 1280, 720, 30
        while self.peek() and self.peek().type in (TokenType.IDENTIFIER, TokenType.NUMBER):
            tok = self.advance()
            if isinstance(tok, Token) and tok.type == TokenType.IDENTIFIER:
                if tok.value == 'width':
                    self.expect(TokenType.EQUALS)
                    width = int(self.expect(TokenType.NUMBER).value)
                elif tok.value == 'height':
                    self.expect(TokenType.EQUALS)
                    height = int(self.expect(TokenType.NUMBER).value)
                elif tok.value == 'fps':
                    self.expect(TokenType.EQUALS)
                    fps = int(self.expect(TokenType.NUMBER).value)
            else:
                break
        return SceneDef(name, width, height, fps)

    def parse_character_def(self):
        self.expect(TokenType.CHARACTER)
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        rig = 'bipedal'; appearance = {}; position = (0, 0); scale = 1.0
        while self.peek() and self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            tok = self.peek()
            if tok.type == TokenType.RIG:
                self.advance()
                rig = self.expect(TokenType.IDENTIFIER).value
            elif tok.type == TokenType.APPEARANCE:
                self.advance()
                while self.peek() and self.peek().type == TokenType.IDENTIFIER:
                    key = self.advance().value
                    if self.peek() and self.peek().type == TokenType.EQUALS:
                        self.advance()
                        appearance[key] = self.advance().value
            elif tok.type == TokenType.POSITION:
                self.advance()
                self.expect(TokenType.LPAREN)
                x = float(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.COMMA)
                y = float(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.RPAREN)
                position = (x, y)
            elif tok.value == 'scale':
                self.advance()
                self.expect(TokenType.EQUALS)
                scale = float(self.expect(TokenType.NUMBER).value)
            else:
                self.advance()
        self.expect(TokenType.DEDENT)
        return CharacterDef(name, rig, appearance, position, scale)

    def parse_camera_def(self):
        self.expect(TokenType.CAMERA)
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        follow = None; zoom = 1.0
        while self.peek() and self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            tok = self.peek()
            if tok.type == TokenType.FOLLOW:
                self.advance()
                follow = self.expect(TokenType.IDENTIFIER).value
            elif tok.type == TokenType.ZOOM:
                self.advance()
                zoom = float(self.expect(TokenType.NUMBER).value)
            else:
                self.advance()
        self.expect(TokenType.DEDENT)
        return CameraDef(name, follow, zoom)

    def parse_action_def(self):
        """Parse an action definition.

        Syntax:
            action kick:
                0.0  right_upper_leg=100 right_lower_leg=-25
                0.3  right_upper_leg=140 right_lower_leg=-80
                0.6  right_upper_leg=100 right_lower_leg=-25
        """
        self.expect(TokenType.ACTION)
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        duration = 0.0
        loop = False
        keyframes = []

        while self.peek() and self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            tok = self.peek()
            # Skip blank lines
            if tok.type == TokenType.NEWLINE:
                self.advance()
                continue

            # Parse duration/loop properties or keyframe lines
            if tok.type == TokenType.IDENTIFIER and tok.value == 'duration':
                self.advance()
                duration = float(self.expect(TokenType.NUMBER).value)
                continue
            if tok.type == TokenType.IDENTIFIER and tok.value == 'loop':
                self.advance()
                val = self.expect(TokenType.IDENTIFIER).value
                loop = val.lower() in ('true', 'yes', '1')
                continue

            # Keyframe line: time bone=angle bone=angle ...
            if tok.type == TokenType.NUMBER:
                t = float(tok.value)
                self.advance()
                # Optional 's' suffix
                if self.peek() and self.peek().value == 's':
                    self.advance()
                pose = {}
                # Parse bone=angle pairs until newline or dedent
                while self.peek() and self.peek().type not in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                    bone = self.expect(TokenType.IDENTIFIER).value
                    self.expect(TokenType.EQUALS)
                    angle = float(self.expect(TokenType.NUMBER).value)
                    pose[bone] = angle
                keyframes.append((t, pose))
                if t > duration:
                    duration = t
                # Skip newline separator
                if self.peek() and self.peek().type == TokenType.NEWLINE:
                    self.advance()
                    # Skip indentation whitespace (already handled by lexer)
                    self.skip_newlines()
                continue
            self.advance()

        self.expect(TokenType.DEDENT)
        return ActionDef(name, duration, loop, keyframes)

    def parse_timeline(self):
        self.expect(TokenType.TIMELINE)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        scenes = {}
        while self.peek() and self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            self.expect(TokenType.SCENE)
            name = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.COLON)
            self.skip_newlines()
            self.expect(TokenType.INDENT)
            events = []
            while self.peek() and self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.peek() and self.peek().type == TokenType.DEDENT:
                    break
                time_val = float(self.expect(TokenType.NUMBER).value)
                if self.peek() and self.peek().value == 's':
                    self.advance()
                # Accept any token as entity name (including keywords like 'camera')
                entity_tok = self.advance()
                entity = entity_tok.value
                self.expect(TokenType.DOT)
                # Accept any token as the action name — 'follow', 'zoom', etc.
                # are lexed as KEYWORDS, so a strict IDENTIFIER requirement
                # would reject main.follow(...) / camera.follow(...).
                action = self.advance().value
                params = {}
                if self.peek() and self.peek().type == TokenType.LPAREN:
                    self.advance()
                    while self.peek() and self.peek().type != TokenType.RPAREN:
                        key_tok = self.advance()
                        key = key_tok.value  # accept keywords like zoom, follow as param keys
                        self.expect(TokenType.EQUALS)
                        val_tok = self.advance()
                        if val_tok.type == TokenType.NUMBER:
                            if '.' in val_tok.value:
                                params[key] = float(val_tok.value)
                            else:
                                params[key] = int(val_tok.value)
                        else:
                            params[key] = val_tok.value.strip('"')
                        if self.peek() and self.peek().type == TokenType.COMMA:
                            self.advance()
                    self.expect(TokenType.RPAREN)
                # Bare key=value params (no parentheses): e.g. dancer.walk x=600
                # The task's .sf format uses this — params continue until the
                # newline/end of the event. Handles numbers and strings.
                while self.peek() and self.peek().type not in (
                    TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                    key_tok = self.advance()
                    key = key_tok.value  # accept keywords like x, y, zoom as keys
                    self.expect(TokenType.EQUALS)
                    val_tok = self.advance()
                    if val_tok.type == TokenType.NUMBER:
                        if '.' in val_tok.value:
                            params[key] = float(val_tok.value)
                        else:
                            params[key] = int(val_tok.value)
                    else:
                        params[key] = val_tok.value.strip('"')
                events.append(TimelineEvent(time_val, f"{entity}.{action}", params))
            scenes[name] = events
            self.expect(TokenType.DEDENT)
        self.expect(TokenType.DEDENT)
        return Timeline(scenes)


# ============================================================ #
# 3. CODE GENERATOR
# ============================================================ #

class CodeGenerator:
    def generate(self, script):
        output = {
            "version": "1.0",
            "scenes": [],
            "characters": [],
            "cameras": [],
            "timeline": {},
            "script": getattr(script, "script", []) or [],
        }
        for scene in script.scenes:
            output["scenes"].append({
                "name": scene.name, "width": scene.width,
                "height": scene.height, "fps": scene.fps
            })
        for char in script.characters:
            output["characters"].append({
                "name": char.name, "rig": char.rig,
                "appearance": char.appearance,
                "position": {"x": char.position[0], "y": char.position[1]},
                "scale": char.scale,
            })
        for cam in script.cameras:
            cam_dict = {"name": cam.name, "zoom": cam.zoom}
            if cam.follow:
                cam_dict["follow"] = cam.follow
            output["cameras"].append(cam_dict)
        # Action definitions
        output["actions"] = []
        for act in script.actions:
            output["actions"].append({
                "name": act.name,
                "duration": act.duration,
                "loop": act.loop,
                "keyframes": [(t, pose) for t, pose in act.keyframes],
            })
        if script.timeline:
            timeline_dict = {}
            for scene_name, events in script.timeline.scenes.items():
                timeline_dict[scene_name] = [
                    {"time": ev.time, "action": ev.action, "params": ev.params}
                    for ev in events
                ]
            output["timeline"] = timeline_dict
        return output


# ============================================================ #
# TEST
# ============================================================ #

test_script = """# StickFrame Script v1.0
scene arena width=1280 height=720 fps=30

character hero:
    rig bipedal
    appearance head_color="#FFD700" body_color="#FF6347"
    position (200, 500)

character villain:
    rig bipedal
    appearance head_color="#8B0000" body_color="#4A0000"
    position (600, 500)

camera main:
    follow hero
    zoom 1.0

timeline:
    scene arena:
        0.0s     hero.idle
        0.5s     villain.idle
        1.0s     hero.walk(direction="right", speed=1.5)
        2.5s     hero.speak(text="You'll never win!")
        3.0s     villain.speak(text="We'll see about that...")
        3.5s     villain.walk(direction="left", speed=1.2)
        4.0s     camera.shake(intensity=0.5)
        4.5s     hero.attack(target=villain, type="punch")
        5.0s     villain.hit(damage=10)
        5.2s     villain.fall
        6.0s     hero.celebrate
"""

if __name__ == '__main__':
    test_script = """# StickFrame Script v1.0
scene arena width=1280 height=720 fps=30

character hero:
    rig bipedal
    appearance head_color="#FFD700" body_color="#FF6347"
    position (200, 500)

character villain:
    rig bipedal
    appearance head_color="#8B0000" body_color="#4A0000"
    position (600, 500)

camera main:
    follow hero
    zoom 1.0

timeline:
    scene arena:
        0.0s     hero.idle
        0.5s     villain.idle
        1.0s     hero.walk(direction="right", speed=1.5)
        2.5s     hero.speak(text="You'll never win!")
        3.0s     villain.speak(text="We'll see about that...")
        3.5s     villain.walk(direction="left", speed=1.2)
        4.0s     camera.shake(intensity=0.5)
        4.5s     hero.attack(target=villain, type="punch")
        5.0s     villain.hit(damage=10)
        5.2s     villain.fall
        6.0s     hero.celebrate
"""

    print("Compiling .sf script...")
    lexer = Lexer(test_script)
    tokens = lexer.tokenize()
    print(f"  Lexer: {len(tokens)} tokens generated")

    parser = Parser(tokens)
    script = parser.parse()
    print(f"  Parser: {len(script.scenes)} scene(s), {len(script.characters)} character(s), "
          f"{len(script.cameras)} camera(s)")
    if script.timeline:
        total_events = sum(len(evts) for evts in script.timeline.scenes.items())
        print(f"  Timeline: {len(script.timeline.scenes)} scene(s), {total_events} event(s)")

    generator = CodeGenerator()
    json_output = generator.generate(script)
    print(f"\n  Code Generator output:")
    print(json.dumps(json_output, indent=2)[:1200] + "...")
    print("\n✓ Compiler pipeline works!")
