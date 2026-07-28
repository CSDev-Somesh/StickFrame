"""
MINI COMPILER: Lexer → Parser → AST → Code Generator
For StickFrame .sf script DSL
"""

import re, json
from dataclasses import dataclass
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
    'zoom': TokenType.ZOOM,
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

    def read_number(self):
        start = self.pos
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
            if ch.isalpha() or ch == '_':
                line, col = self.line, self.col
                word = self.read_identifier()
                tok_type = KEYWORDS.get(word, TokenType.IDENTIFIER)
                self.tokens.append(Token(tok_type, word, line, col))
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
    name: str; rig: str; appearance: dict; position: tuple

@dataclass
class CameraDef:
    name: str; follow: str; zoom: float

@dataclass
class TimelineEvent:
    time: float; action: str; params: dict

@dataclass
class Timeline:
    scenes: dict

@dataclass
class Script:
    scenes: list; characters: list; cameras: list; timeline: Timeline

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
            else:
                self.advance()
            self.skip_newlines()
        return script

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
        rig = 'bipedal'; appearance = {}; position = (0, 0)
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
            else:
                self.advance()
        self.expect(TokenType.DEDENT)
        return CharacterDef(name, rig, appearance, position)

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
                action = self.expect(TokenType.IDENTIFIER).value
                params = {}
                if self.peek() and self.peek().type == TokenType.LPAREN:
                    self.advance()
                    while self.peek() and self.peek().type != TokenType.RPAREN:
                        key = self.expect(TokenType.IDENTIFIER).value
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
            "timeline": {}
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
                "position": {"x": char.position[0], "y": char.position[1]}
            })
        for cam in script.cameras:
            cam_dict = {"name": cam.name, "zoom": cam.zoom}
            if cam.follow:
                cam_dict["follow"] = cam.follow
            output["cameras"].append(cam_dict)
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
