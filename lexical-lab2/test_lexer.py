#!/usr/bin/env python3
import unittest
from pathlib import Path

from lab2_lexer import Lexer


class Variant6LexerTests(unittest.TestCase):
    def test_valid_tokens(self):
        tokens, errors = Lexer("a := not (b and 1) or c xor 0;").scan()
        self.assertFalse(errors)
        self.assertEqual([token.kind for token in tokens], [
            "Идентификатор", "Знак присваивания", "Логическая операция",
            "Левая скобка", "Идентификатор", "Логическая операция",
            "Логическая константа", "Правая скобка", "Логическая операция",
            "Идентификатор", "Логическая операция", "Логическая константа",
            "Разделитель выражений",
        ])

    def test_comments_are_ignored_and_positions_continue(self):
        tokens, errors = Lexer("{ long\n comment }\na:=0").scan()
        self.assertFalse(errors)
        self.assertEqual([token.lexeme for token in tokens], ["a", ":=", "0"])
        self.assertEqual((tokens[0].line, tokens[0].column), (3, 1))

    def test_invalid_tokens_are_reported_and_scanning_continues(self):
        tokens, errors = Lexer("a := 10; b : 1; @ c := 0").scan()
        self.assertEqual([token.lexeme for token in tokens], ["a", ":=", ";", "b", "1", ";", "c", ":=", "0"])
        self.assertEqual(len(errors), 3)

    def test_limits(self):
        good = "a" * 32
        bad = "a" * 33
        tokens, errors = Lexer(f"{good} := 1; {bad} := 0").scan()
        self.assertEqual(tokens[0].lexeme, good)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
