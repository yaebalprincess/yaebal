#!/usr/bin/env python3
"""Lexical analyzer for Laboratory work 2, variant 6.

The scanner recognizes the token alphabet from the assignment.  It deliberately
does not perform syntax analysis: malformed token text is reported while the
remaining input is scanned so that one run produces a complete token table.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_IDENTIFIER_LENGTH = 32
KEYWORDS = {"or", "xor", "and", "not"}
IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class Token:
    number: int
    lexeme: str
    kind: str
    value: str
    line: int
    column: int


@dataclass
class LexicalError:
    message: str
    lexeme: str
    line: int
    column: int


class Lexer:
    """Single-pass scanner with line/column tracking and error recovery."""

    def __init__(self, source: str):
        self.source = source
        self.i = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
        self.errors: list[LexicalError] = []

    def _advance(self) -> str:
        ch = self.source[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _take(self, start: int) -> str:
        return self.source[start:self.i]

    def _add_token(self, lexeme: str, kind: str, value: str, line: int, column: int) -> None:
        self.tokens.append(Token(len(self.tokens) + 1, lexeme, kind, value, line, column))

    def _error(self, message: str, lexeme: str, line: int, column: int) -> None:
        self.errors.append(LexicalError(message, lexeme, line, column))

    def scan(self) -> tuple[list[Token], list[LexicalError]]:
        while self.i < len(self.source):
            ch = self.source[self.i]
            if ch.isspace():
                self._advance()
                continue
            start, line, column = self.i, self.line, self.column
            if ch == "{":
                self._scan_comment(start, line, column)
            elif ch.isalpha() and ch.isascii():
                self._scan_word(start, line, column)
            elif ch.isdigit():
                self._scan_digit_run(start, line, column)
            elif ch == "_":
                self._scan_bad_word(start, line, column, "идентификатор должен начинаться с латинской буквы")
            elif ch == ":":
                self._advance()
                if self.i < len(self.source) and self.source[self.i] == "=":
                    self._advance()
                    self._add_token(":=", "Знак присваивания", ":=", line, column)
                else:
                    self._error("ожидался символ '=' после ':'", ":", line, column)
            elif ch in ";()":
                self._advance()
                names = {";": "Разделитель выражений", "(": "Левая скобка", ")": "Правая скобка"}
                self._add_token(ch, names[ch], ch, line, column)
            elif ch == "}":
                self._advance()
                self._error("закрывающая скобка комментария без открывающей", ch, line, column)
            else:
                self._advance()
                self._error("недопустимый символ входного языка", ch, line, column)
        return self.tokens, self.errors

    def _scan_comment(self, start: int, line: int, column: int) -> None:
        self._advance()  # {
        while self.i < len(self.source) and self.source[self.i] != "}":
            self._advance()
        if self.i < len(self.source):
            self._advance()  # }
        else:
            self._error("незавершённый комментарий: отсутствует '}'", self.source[start:self.i], line, column)

    def _scan_word(self, start: int, line: int, column: int) -> None:
        match = WORD_RE.match(self.source, self.i)
        assert match is not None
        while self.i < match.end():
            self._advance()
        lexeme = self._take(start)
        if lexeme in KEYWORDS:
            self._add_token(lexeme, "Логическая операция", lexeme, line, column)
        elif len(lexeme) > MAX_IDENTIFIER_LENGTH:
            self._error(f"длина идентификатора превышает {MAX_IDENTIFIER_LENGTH} символа", lexeme, line, column)
        else:
            self._add_token(lexeme, "Идентификатор", lexeme, line, column)

    def _scan_digit_run(self, start: int, line: int, column: int) -> None:
        match = WORD_RE.match(self.source, self.i)
        assert match is not None
        while self.i < match.end():
            self._advance()
        lexeme = self._take(start)
        if lexeme in {"0", "1"}:
            self._add_token(lexeme, "Логическая константа", lexeme, line, column)
        else:
            self._error("допустимы только логические константы 0 и 1", lexeme, line, column)

    def _scan_bad_word(self, start: int, line: int, column: int, message: str) -> None:
        match = WORD_RE.match(self.source, self.i)
        assert match is not None
        while self.i < match.end():
            self._advance()
        self._error(message, self._take(start), line, column)


def scan_file(path: Path) -> tuple[list[Token], list[LexicalError]]:
    return Lexer(path.read_text(encoding="utf-8")).scan()


def render_table(tokens: list[Token]) -> str:
    headers = ("№", "Лексема", "Тип", "Значение", "Строка", "Столбец")
    rows = [headers] + [tuple(str(getattr(t, field)) for field in ("number", "lexeme", "kind", "value", "line", "column")) for t in tokens]
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    line = "  ".join("-" * width for width in widths)
    out = ["  ".join(value.ljust(widths[i]) for i, value in enumerate(headers)), line]
    out.extend("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in rows[1:])
    return "\n".join(out)


def write_csv(path: Path, tokens: list[Token]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["number", "lexeme", "kind", "value", "line", "column"])
        writer.writeheader()
        writer.writerows(asdict(token) for token in tokens)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Лексический анализатор, лабораторная работа №2, вариант 6")
    parser.add_argument("input", type=Path, help="входной текстовый файл")
    parser.add_argument("--csv", type=Path, help="сохранить таблицу лексем в CSV")
    parser.add_argument("--json", type=Path, help="сохранить результат анализа в JSON")
    args = parser.parse_args(argv)
    try:
        tokens, errors = scan_file(args.input)
    except (OSError, UnicodeError) as exc:
        print(f"Ошибка чтения файла: {exc}", file=sys.stderr)
        return 2
    print(f"Файл: {args.input}")
    print(f"Распознано лексем: {len(tokens)}")
    print(render_table(tokens))
    if errors:
        print(f"\nЛексические ошибки: {len(errors)}", file=sys.stderr)
        for error in errors:
            print(f"  строка {error.line}, столбец {error.column}: {error.message}; фрагмент {error.lexeme!r}", file=sys.stderr)
    else:
        print("\nЛексических ошибок не обнаружено.")
    if args.csv:
        write_csv(args.csv, tokens)
    if args.json:
        args.json.write_text(json.dumps({"tokens": [asdict(t) for t in tokens], "errors": [asdict(e) for e in errors]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
