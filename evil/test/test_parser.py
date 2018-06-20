import unittest

from evil.parser import *

class ParserTest(unittest.TestCase):
    def test_parse_label(self):
        self.assertEqual(Label('foo'), Statement.parse('foo:'))

    def test_parse_constant_definition(self):
        self.assertEqual(ConstantDefinition('FOO', NumericExpression(1)),
                         Statement.parse('FOO = 1'))

        self.assertEqual(ConstantDefinition('FOO', CharacterExpression('a')),
                         Statement.parse("FOO = 'a'"))
        self.assertEqual(ConstantDefinition('FOO', CharacterExpression('\x42')),
                         Statement.parse("FOO = '\x42'"))

        self.assertEqual(ConstantDefinition('FOO', ConstantExpression('BAR')),
                         Statement.parse('FOO = BAR'))

        self.assertEqual(ConstantDefinition('FOO',
                                            BinaryExpression(NumericExpression(1),
                                                             '+',
                                                             NumericExpression(2))),
                         Statement.parse('FOO = 1 + 2'))

    def test_parse_data(self):
        self.assertEqual(Data(DataType.from_fmt('b'),
                              ExpressionList([NumericExpression(1),
                                              NumericExpression(2),
                                              NumericExpression(3)])),
                         Statement.parse('db 1, 2, 3'))
        self.assertEqual(Data(DataType.from_fmt('w'),
                              ExpressionList([NumericExpression(1),
                                              NumericExpression(2),
                                              NumericExpression(3)])),
                         Statement.parse('dw 1, 2, 3'))

        self.assertEqual(Data(DataType.from_fmt('b'),
                              ExpressionList([CharacterExpression('a'),
                                              CharacterExpression('b'),
                                              CharacterExpression('\x42')])),
                         Statement.parse('db "ab\x42"'))
