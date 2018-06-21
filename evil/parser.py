import string
import logging

from typing import NamedTuple, List, Union, Callable, Optional, Mapping

from evil.cpu import Register, CPU, Operation
from evil.utils import tokenize
from evil.memory import DataType


IDENTIFIER_CHARS = string.ascii_letters + string.digits + '_.'


def matches(tokens: List[str],
            pattern: List[Union[Callable[[str], bool], str]]) -> bool:
    if len(tokens) != len(pattern):
        return False

    for tok, pat in zip(tokens, pattern):
        if isinstance(pat, str):
            if tok != pat:
                return False
        elif not pat(tok):
            return False

    return True


def extract_parens(tokens: List[str]):
    assert tokens[0] in ('(', '[', '{')

    PAIRS = {
        '(': ')',
        '[': ']',
        '{': '}'
    }

    stack = []
    for idx, tok in enumerate(tokens):
        if tok in PAIRS:
            stack.append(tok)
        elif tok in PAIRS.values():
            if tok == PAIRS[stack[-1]]:
                stack.pop()
            else:
                raise ValueError('mismatched parens: expected %s, got %s' % (PAIRS[stack[-1]], tok))

        if not stack:
            return tokens[0:idx + 1]
    raise ValueError('mismatched parens - unclosed: %s' % stack)


def build_expression_tree(tokens: List[str]):
    logging.debug('build_expression_tree %s' % (tokens,))
    tree = []
    idx = 0

    while idx < len(tokens):
        if tokens[idx] == '(':
            parens = extract_parens(tokens[idx:])
            tree.append(build_expression_tree(parens[1:-1]))
            idx += len(parens)
        else:
            tree.append(tokens[idx])
            idx += 1

    def parse_expression(text: Union[Expression, str]):
        if not isinstance(text, str):
            return text
        try:
            return NumericExpression(int(text, 0))
        except ValueError:
            pass
        if Match.character(text):
            return CharacterExpression(eval(text))
        if Match.identifier(text):
            return ConstantExpression(text)
        return text

    tree = [parse_expression(e) for e in tree]

    for op_set in (('<<', '>>'),
                   ('*', '/'),
                   ('+', '-')):
        idx = 0
        while idx < len(tree) - 1:
            if tree[idx] in op_set:
                if idx == 0:
                    tree[:2] = [UnaryExpression(tree[0], tree[1])]
                else:
                    tree[idx - 1:idx + 2] = [BinaryExpression(tree[idx - 1],
                                                              tree[idx],
                                                              tree[idx + 1])]
            else:
                idx += 1

    logging.debug('tree = %s' % (tree,))

    if len(tree) == 1:

        tree = tree[0]

    logging.debug('return = %s' % (tree,))
    return tree


def comma_separated_groups(tokens: List[str]):
    while tokens:
        try:
            comma_idx = tokens.index(',')
            yield tokens[:comma_idx]
            tokens = tokens[comma_idx + 1:]
        except ValueError:
            yield tokens
            tokens = []


class Match:
    @staticmethod
    def identifier(token: str):
        return all(c in IDENTIFIER_CHARS for c in token)

    @staticmethod
    def character(token: str):
        if len(token) > len(r"'\x00000000'"):
            return False

        try:
            value = eval(token)
            if not isinstance(value, str) or len(value) != 1:
                return False
        except:
            return False

        return True

    @staticmethod
    def string_literal(token: str):
        if len(token) < 2 or token[0] != '"' or token[-1] != '"':
            return False

        try:
            value = eval(token)
            if not isinstance(value, str):
                return False
        except:
            return False

        return True


class Statement:
    @staticmethod
    def parse(text: str) -> Optional['Statement']:
        text = text.strip()
        tokens = tokenize(text)

        if not tokens:
            return None

        if matches(tokens, [Match.identifier, ':']):
            return Label(tokens[0])
        if matches(tokens[:2], [Match.identifier, '=']):
            return ConstantDefinition(tokens[0], Expression.build(tokens[2:]))
        if matches(tokens[:1], [Match.identifier]):
            if tokens[0] in Data.DATATYPES:
                return Data.build(tokens)
            else:
                return Instruction.build(tokens)
        if matches(tokens[:1], [';']):
            return None
        raise ValueError('unable to parse statement: %s', text)


class ConstantDefinition(NamedTuple, Statement):
    """ NAME = EXPR """
    name: str
    value: 'Expression'



class Data(NamedTuple, Statement):
    """
    db EXPR [, EXPR]*
    db "foo"
    """
    values: List['Expression']


class Label(NamedTuple, Statement):
    name: str


class Expression:
    @staticmethod
    def build(tokens: List[str]) -> 'Expression':
        try:
            logging.debug('Expression.build: %s' % (tokens,))
            return build_expression_tree(tokens)
        except ValueError as err:
            raise ValueError('unable to form a valid expression from tokens: %s' % (tokens,)) from err


class NumericExpression(NamedTuple, Expression):
    """ 123 """
    value: int


class CharacterExpression(NamedTuple, NumericExpression):
    """ 'C' """
    value: str


class ConstantExpression(NamedTuple, Expression):
    """ Identifier """
    name: str


class UnaryExpression(NamedTuple, Expression):
    """ UnaryOperator Expression """
    operator: str
    operand: Expression


class BinaryExpression(NamedTuple, Expression):
    """ Expression BinaryOperator Expression """
    lhs: Expression
    operator: str
    rhs: Expression

class ExpressionList(NamedTuple):
    """
    EXPR [, EXPR]*
    "foo"
    """
    subexpressions: List[Expression]

    @staticmethod
    def build(tokens: List[str]):
        args = []

        for group in comma_separated_groups(tokens):
            if matches(group, [Match.string_literal]):
                args += [CharacterExpression(c) for c in eval(group[0])]
            else:
                args.append(Expression.build(group))

        return ExpressionList(args)

    def __iter__(self):
        return iter(self.subexpressions)


class ArgumentList(NamedTuple):
    """
    Like ExpressionList, but can contain register references
    """
    arguments: List[Union[Register, Expression]]

    @staticmethod
    def build(tokens: List[str]):
        args = []

        for group in comma_separated_groups(tokens):
            try:
                if len(group) == 1:
                    args.append(Register.by_name(group[0].upper()))
                    continue
            except:
                pass

            if matches(group, [Match.string_literal]):
                args += [CharacterExpression(c) for c in eval(group[0])]
            else:
                args.append(Expression.build(group))

        return ArgumentList(args)


class Instruction(NamedTuple, Statement):
    """ foo bar, baz """
    operation: Operation
    args: ArgumentList

    @staticmethod
    def build(tokens: List[str]):
        return Instruction(CPU.OPERATIONS_BY_MNEMONIC[tokens[0]],
                           ArgumentList.build(tokens[1:]))


class Data(NamedTuple, Statement):
    """ db/a/w ARGUMENT_LIST """
    datatype: DataType
    values: ArgumentList

    DATATYPES = {
        'db': DataType.from_fmt('b'),
        'da': DataType.from_fmt('a'),
        'dw': DataType.from_fmt('w'),
    }

    @staticmethod
    def build(tokens: List[str]):
        return Data(Data.DATATYPES[tokens[0]],
                    ExpressionList.build(tokens[1:]))
