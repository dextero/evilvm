"""
Assembly -> bytecode compiler and utilities.
"""
import collections
import logging
from typing import List, NamedTuple, Sequence, Union, Set

from evil.cpu import CPU, Register, Operation
from evil.utils import tokenize
from evil.endianness import Endianness
from evil.memory import Memory, ExtendableMemory, DataType
from evil.parser import *


class Bytecode(list):
    """
    A list of opcodes that ensures all elements can be encoded on given number
    of bits.
    """
    def __init__(self, char_bit: int):
        super().__init__()
        self._char_bit = char_bit

    @property
    def char_bit(self):
        """
        Number of bits per element. No element may be >= 2**char_bit.
        """
        return self._char_bit

    def _validate(self, val: int):
        assert isinstance(val, int)
        assert 0 <= val < 2**self.char_bit

    def __setitem__(self, idx: int, val: int):
        self._validate(val)
        return super().__setitem__(idx, val)

    def append(self, val: int):
        self._validate(val)
        return super().append(val)

    def __iadd__(self, other: Sequence[int]):
        for val in other:
            self._validate(val)
        return super().__iadd__(other)

    @classmethod
    def from_memory(cls, mem: Memory):
        bytecode = cls(mem.char_bit)
        bytecode += mem
        return bytecode

class Assembler:
    """
    Assembly language to bytecode converter.

    This is a two-pass process:
    * First pass turns source into intermediate representation, i.e. a list of
      Statements. During this pass, all labels and its positions are discovered
      and noted in self._labels. Similarly, all constants are noted in
      self._constants.
    * Second pass converts intermediate representation into final bytecode,
      filling in label and constant values if necessary.
    """
    class LineIR(NamedTuple):
        source: str
        statement: Statement
        bytecode: List[int]

    def __init__(self, char_bit: int):
        self._char_bit = char_bit
        self._reset()

    def _reset(self):
        """
        Clears the assembler state.
        """
        self._constants = {}
        # intermediate representation - list of Statements
        self._intermediate = []
        self._curr_offset = 0

    def _append_statement(self, line: str, stmt: Statement):
        logging.debug('%-40s %s' % (line, stmt))

        if isinstance(stmt, ConstantDefinition):
            if stmt.name in self._constants:
                raise ValueError('multiple definitions of constant %s' % stmt.name)
            logging.debug('constant: %s = %s' % stmt)
            self._constants[stmt.name] = stmt.value
            stmt = None
        elif isinstance(stmt, Label):
            if stmt.name in self._constants:
                raise ValueError('multiple definitions of constant %s' % stmt.name)
            self._constants[stmt.name] = self._curr_offset
            stmt = None
        elif isinstance(stmt, Data):
            self._curr_offset += stmt.datatype.size_bytes * len(stmt.values.subexpressions)
        elif isinstance(stmt, Instruction):
            self._curr_offset += stmt.operation.size_bytes

        self._intermediate.append(Assembler.LineIR(line, stmt, bytecode=[]))

    def _resolve_expression(self,
                            expr: Expression,
                            already_resolved: Set[str] = None) -> int:
        logging.debug('%s = ?' % (expr,))
        if not already_resolved:
            already_resolved = set()

        if isinstance(expr, NumericExpression):
            logging.debug('NumericExpression: %d' % expr.value)
            return expr.value
        elif isinstance(expr, CharacterExpression):
            logging.debug('CharacterExpression: %d' % ord(expr.value))
            return ord(expr.value)
        elif isinstance(expr, ConstantExpression):
            if expr.name in already_resolved:
                raise ValueError('circular constant definition: %s' % expr.name)
            val = self._constants[expr.name]
            if not isinstance(val, int):
                val = self._resolve_expression(self._constants[expr.name],
                                               already_resolved | set(expr.name))
                self._constants[expr.name] = val
            else:
                logging.debug('alredy resolved: %s = %s' % (expr.name, val))
            logging.debug('ConstantExpression %s' % (val,))
            return val
        elif isinstance(expr, UnaryExpression):
            logging.debug('UnaryExpression: %s' % (expr,))
            if expr.operator == 'sizeof':
                assert isinstance(expr.operand, ConstantExpression)
                try:
                    return DataType.from_fmt(expr.operand.name).size_bytes
                except KeyError:
                    return CPU.OPERATIONS_BY_MNEMONIC[expr.operand.name].size_bytes
            elif expr.operator == 'alignof':
                assert isinstance(expr.operand, ConstantExpression)
                return DataType.from_fmt(expr.operand.name).alignment
            else:
                return eval(expr.operator + str(self._resolve_expression(expr.operand)))
        elif isinstance(expr, BinaryExpression):
            logging.debug('BinaryExpression: %s' % (expr,))
            return eval(str(self._resolve_expression(expr.lhs))
                        + expr.operator.replace('/', '//')  # TODO: hack for integer division
                        + str(self._resolve_expression(expr.rhs)))
        else:
            raise AssertionError('unknown expression type: %r' % (expr,))

    def _compile(self) -> Memory:
        """
        Fills .bytecode field of IRElements in self._intermediate,
        returns memory block with whole source bytecode
        """
        curr_ip = 0 # instruction pointer value at the point of running current op
        mem = ExtendableMemory(self._char_bit)

        for line in self._intermediate:
            try:
                logging.debug('compile: %s', line.source)
                if not line.statement:
                    continue

                prev_ip = curr_ip

                if isinstance(line.statement, Data):
                    for value in line.statement.values:
                        mem.append(self._resolve_expression(value),
                                   line.statement.datatype,
                                   Endianness.Big)
                elif isinstance(line.statement, Instruction):
                    op = line.statement.operation
                    curr_ip = len(mem) + op.size_bytes

                    mem.append(op.opcode,
                               DataType.from_fmt('b'),
                               Endianness.Little)

                    for idx, arg in enumerate(line.statement.args.arguments):
                        arg_datatype = DataType.from_fmt(op.arg_def[idx])

                        if isinstance(arg, Register):
                            mem.append(arg.value,
                                       arg_datatype,
                                       op.args_endianness)
                        else:
                            val = self._resolve_expression(arg)
                            mem.append(self._resolve_expression(arg),
                                       arg_datatype,
                                       op.args_endianness)
                else:
                    raise AssertionError('unhandled IR type: %s' % type(line.statement).__name__)

                curr_ip = len(mem)
                line.bytecode[:] = mem[prev_ip:]
            except Exception as err:
                raise Exception('could not assemble line: %s' % (line.source,)) from err

        return mem

    def _log_source(self):
        bc_fmt_size = len('%x' % (2**self._char_bit - 1))
        bc_fmt = '%0{0}x'.format(bc_fmt_size)

        def bytecode_hex(bytecode):
            return ' '.join(bc_fmt % b for b in bytecode)

        max_line_len = max(len(ir.source) for ir in self._intermediate)
        line_fmt = '%08x  %-{0}s  %s'.format(max_line_len)

        logging.debug('--- ASSEMBLY ---')

        addr = 0
        for line_ir in self._intermediate:
            logging.debug(line_fmt % (addr, line_ir.source, bytecode_hex(line_ir.bytecode)))
            addr += len(line_ir.bytecode)

        logging.debug('--- ASSEMBLY END ---')

    def assemble_to_memory(self, source: str) -> Memory:
        self._reset()

        instructions = source.split('\n')
        for lineno, instr in enumerate(instructions, start=1):
            try:
                self._append_statement(instr, Statement.parse(instr))
            except Exception as err:
                raise SyntaxError('Error while parsing line %d (%s)' % (lineno, instr))

        mem = self._compile()
        self._log_source()
        return mem

    def assemble(self, source: str) -> Bytecode:
        return Bytecode.from_memory(self.assemble_to_memory(source))
