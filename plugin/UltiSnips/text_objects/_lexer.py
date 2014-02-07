#!/usr/bin/env python
# encoding: utf-8

"""
Not really a lexer in the classical sense, but code to convert snippet
definitions into logical units called Tokens.
"""

import string
import re

from UltiSnips.geometry import Position
from UltiSnips.compatibility import as_unicode

__all__ = [
    "tokenize", "EscapeCharToken", "VisualToken", "TransformationToken",
    "TabStopToken", "MirrorToken", "PythonCodeToken", "VimLCodeToken",
    "ShellCodeToken"
]

class _TextIterator(object):
    """Helper class to make iterating over text easier."""

    def __init__(self, text, offset):
        self._text = as_unicode(text)
        self._line = offset.line
        self._col = offset.col

        self._idx = 0

    def __iter__(self):
        """Iterator interface."""
        return self

    def next(self):
        """Returns the next character. Part of the iterator interface."""
        if self._idx >= len(self._text):
            raise StopIteration

        rv = self._text[self._idx]
        if self._text[self._idx] in ('\n', '\r\n'):
            self._line += 1
            self._col = 0
        else:
            self._col += 1
        self._idx += 1

        return rv

    def peek(self, count=1):
        """Returns the next 'count' characters without advancing the stream."""
        if count > 1: # This might return '' if nothing is found
            return self._text[self._idx:self._idx + count]
        try:
            return self._text[self._idx]
        except IndexError:
            return None

    @property
    def pos(self):
        """Current position in the text."""
        return Position(self._line, self._col)

def _unescape(text):
    """Removes escaping from 'text'."""
    rv = ""
    i = 0
    while i < len(text):
        if i+1 < len(text) and text[i] == '\\':
            rv += text[i+1]
            i += 1
        else:
            rv += text[i]
        i += 1
    return rv

def _parse_number(stream):
    """
    Expects the stream to contain a number next, returns the number
    without consuming any more bytes
    """
    rv = ""
    while stream.peek() and stream.peek() in string.digits:
        rv += stream.next()

    return int(rv)

def _parse_till_closing_brace(stream):
    """
    Returns all chars till a non-escaped } is found. Other
    non escaped { are taken into account and skipped over.

    Will also consume the closing }, but not return it
    """
    rv = ""
    in_braces = 1
    while True:
        if EscapeCharToken.starts_here(stream, '{}'):
            rv += stream.next() + stream.next()
        else:
            char = stream.next()
            if char == '{':
                in_braces += 1
            elif char == '}':
                in_braces -= 1
            if in_braces == 0:
                break
            rv += char
    return rv

def _parse_till_unescaped_char(stream, chars):
    """
    Returns all chars till a non-escaped char is found.

    Will also consume the closing char, but and return it as second
    return value
    """
    rv = ""
    while True:
        escaped = False
        for char in chars:
            if EscapeCharToken.starts_here(stream, char):
                rv += stream.next() + stream.next()
                escaped = True
        if not escaped:
            char = stream.next()
            if char in chars:
                break
            rv += char
    return rv, char

class Token(object):
    """Represents a Token as parsed from a snippet definition."""

    def __init__(self, gen, indent):
        self.initial_text = as_unicode("")
        self.start = gen.pos
        self._parse(gen, indent)
        self.end = gen.pos

    def _parse(self, stream, indent):
        """Parses the token from 'stream' with the current 'indent'."""
        pass # Does nothing

class TabStopToken(Token):
    """${1:blub}"""
    CHECK = re.compile(r'^\${\d+[:}]')

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(10)) is not None

    def _parse(self, stream, indent):
        stream.next() # $
        stream.next() # {

        self.number = _parse_number(stream)

        if stream.peek() == ":":
            stream.next()
        self.initial_text = _parse_till_closing_brace(stream)

    def __repr__(self):
        return "TabStopToken(%r,%r,%r,%r)" % (
            self.start, self.end, self.number, self.initial_text
        )

class VisualToken(Token):
    """${VISUAL}"""
    CHECK = re.compile(r"^\${VISUAL[:}/]")

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(10)) is not None

    def _parse(self, stream, indent):
        for _ in range(8): # ${VISUAL
            stream.next()

        if stream.peek() == ":":
            stream.next()
        self.alternative_text, char = _parse_till_unescaped_char(stream, '/}')
        self.alternative_text = _unescape(self.alternative_text)

        if char == '/': # Transformation going on
            try:
                self.search = _parse_till_unescaped_char(stream, '/')[0]
                self.replace = _parse_till_unescaped_char(stream, '/')[0]
                self.options = _parse_till_closing_brace(stream)
            except StopIteration:
                raise RuntimeError(
                    "Invalid ${VISUAL} transformation! Forgot to escape a '/'?")
        else:
            self.search = None
            self.replace = None
            self.options = None

    def __repr__(self):
        return "VisualToken(%r,%r)" % (
            self.start, self.end
        )

class TransformationToken(Token):
    """${1/match/replace/options}"""

    CHECK = re.compile(r'^\${\d+\/')

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(10)) is not None

    def _parse(self, stream, indent):
        stream.next() # $
        stream.next() # {

        self.number = _parse_number(stream)

        stream.next() # /

        self.search = _parse_till_unescaped_char(stream, '/')[0]
        self.replace = _parse_till_unescaped_char(stream, '/')[0]
        self.options = _parse_till_closing_brace(stream)

    def __repr__(self):
        return "TransformationToken(%r,%r,%r,%r,%r)" % (
            self.start, self.end, self.number, self.search, self.replace
        )

class MirrorToken(Token):
    """$1"""
    CHECK = re.compile(r'^\$\d+')

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(10)) is not None

    def _parse(self, stream, indent):
        stream.next() # $
        self.number = _parse_number(stream)

    def __repr__(self):
        return "MirrorToken(%r,%r,%r)" % (
            self.start, self.end, self.number
        )

class EscapeCharToken(Token):
    """\\n"""
    @classmethod
    def starts_here(cls, stream, chars=r'{}\$`'):
        """Returns true if this token starts at the current position in
        'stream'."""
        cs = stream.peek(2)
        if len(cs) == 2 and cs[0] == '\\' and cs[1] in chars:
            return True

    def _parse(self, stream, indent):
        stream.next() # \
        self.initial_text = stream.next()

    def __repr__(self):
        return "EscapeCharToken(%r,%r,%r)" % (
            self.start, self.end, self.initial_text
        )

class ShellCodeToken(Token):
    """`! echo "hi"`"""
    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return stream.peek(1) == '`'

    def _parse(self, stream, indent):
        stream.next() # `
        self.code = _parse_till_unescaped_char(stream, '`')[0]

    def __repr__(self):
        return "ShellCodeToken(%r,%r,%r)" % (
            self.start, self.end, self.code
        )

class PythonCodeToken(Token):
    """`!p snip.rv = "Hi"`"""
    CHECK = re.compile(r'^`!p\s')

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(4)) is not None

    def _parse(self, stream, indent):
        for _ in range(3):
            stream.next() # `!p
        if stream.peek() in '\t ':
            stream.next()

        code = _parse_till_unescaped_char(stream, '`')[0]

        # Strip the indent if any
        if len(indent):
            lines = code.splitlines()
            self.code = lines[0] + '\n'
            self.code += '\n'.join([l[len(indent):]
                        for l in lines[1:]])
        else:
            self.code = code
        self.indent = indent

    def __repr__(self):
        return "PythonCodeToken(%r,%r,%r)" % (
            self.start, self.end, self.code
        )

class VimLCodeToken(Token):
    """`!v g:hi`"""
    CHECK = re.compile(r'^`!v\s')

    @classmethod
    def starts_here(cls, stream):
        """Returns true if this token starts at the current position in
        'stream'."""
        return cls.CHECK.match(stream.peek(4)) is not None

    def _parse(self, stream, indent):
        for _ in range(4):
            stream.next() # `!v
        self.code = _parse_till_unescaped_char(stream, '`')[0]

    def __repr__(self):
        return "VimLCodeToken(%r,%r,%r)" % (
            self.start, self.end, self.code
        )

class EndOfTextToken(Token):
    """Appears at the end of the text."""
    def __repr__(self):
        return "EndOfText(%r)" % self.end

__ALLOWED_TOKENS = [
    EscapeCharToken, VisualToken, TransformationToken, TabStopToken,
    MirrorToken, PythonCodeToken, VimLCodeToken, ShellCodeToken
]
def tokenize(text, indent, offset):
    """Returns an iterator of tokens of 'text'['offset':] which is assumed to
    have 'indent' as the whitespace of the begging of the lines."""
    stream = _TextIterator(text, offset)
    try:
        while True:
            done_something = False
            for token in __ALLOWED_TOKENS:
                if token.starts_here(stream):
                    yield token(stream, indent)
                    done_something = True
                    break
            if not done_something:
                stream.next()
    except StopIteration:
        yield EndOfTextToken(stream, indent)
