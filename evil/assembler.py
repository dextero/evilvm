"""
Assembly -> bytecode compiler and utilities.
"""
import collections
import logging
from typing import List, NamedTuple, Sequence

from evil.cpu import CPU, Packer, Register, Operation
from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value


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

class Assembler:
    """
    Assembly language to bytecode converter.

    This is a two-pass process:
    * First pass turns source into intermediate representation, i.e. a list of
      Operation or other classes defined below. During this pass, all labels
      and its positions are discovered and noted in self._labels.
    * Second pass converts intermediate representation into final bytecode,
      filling in label values if necessary.
    """

    class Immediate(NamedTuple):
        """ Literal value. """
        value: int
        endianness: Endianness
        size_bytes: int

    class RegisterRef(NamedTuple):
        """ CPU register reference. """
        reg: Register
        endianness: Endianness
        size_bytes: int = Packer.calcsize('r')

    class LabelRef(NamedTuple):
        """ Named label reference. """
        label: str
        endianness: Endianness
        relative: bool
        size_bytes: int = Packer.calcsize('a')

    def __init__(self, char_bit: int):
        self._char_bit = char_bit
        self._reset()

    def _reset(self):
        """
        Clears the assembler state.
        """
        self._labels = {}
        self._label_refs = collections.defaultdict(list)
        # intermediate representation - list of:
        # Operation, Immediate, RegisterRef, LabelRef
        self._intermediate = []
        self._curr_offset = 0

    @staticmethod
    def _parse_immediate(text: str,
                         operation: Operation,
                         size_bytes: int) -> 'Assembler.Immediate':
        if len(text) == 3 and text[0] == "'" == text[-1]:
            value = ord(text[1])
        else:
            value = int(text, 0)

        return Assembler.Immediate(value=value,
                                   size_bytes=size_bytes,
                                   endianness=operation.args_endianness)

    def _parse_arg(self,
                   text: str,
                   operation: Operation,
                   arg_type: str):
        """
        Parses an instruction argument, returning its numeric value.
        """
        if arg_type == 'r':
            return Assembler.RegisterRef(Register.by_name(text.upper()),
                                         endianness=operation.args_endianness)
        elif arg_type in ('b', 'w', 'a'):
            try:
                # literal value
                return self._parse_immediate(text,
                                             operation,
                                             Packer.calcsize(arg_type))
            except ValueError:
                # label
                return Assembler.LabelRef(label=text,
                                          endianness=operation.args_endianness,
                                          relative=operation.mnemonic.endswith('.rel'))
        else:
            raise ValueError('unsupported argument type: %s' % arg_type)

    def _append_instruction(self, line: str):
        """
        Parses LINE as an instruction and appends its intermediate
        representation to self._intermediate.
        """
        if ' ' in line:
            mnemonic, argline = line.split(' ', maxsplit=1)
        else:
            mnemonic = line
            argline = ''

        try:
            operation = CPU.OPERATIONS_BY_MNEMONIC[mnemonic]
        except KeyError as err:
            raise KeyError('invalid opcode: %s' % mnemonic) from err

        op_ir = [operation]
        for idx, arg in enumerate(argline.split()):
            arg = arg.strip(',') # TODO: UGLYYY
            op_ir.append(self._parse_arg(arg, operation, operation.arg_def[idx]))

        self._intermediate += op_ir
        self._curr_offset += operation.size_bytes

    def _compile_immediate(self, imm: 'Assembler.Immediate') -> List[int]:
        return bytes_from_value(endianness=imm.endianness,
                                value=imm.value,
                                char_bit=self._char_bit,
                                num_bytes=imm.size_bytes)

    def _compile_register_ref(self, reg: 'Assembler.RegisterRef') -> List[int]:
        return bytes_from_value(endianness=reg.endianness,
                                value=reg.reg.value,
                                char_bit=self._char_bit,
                                num_bytes=reg.size_bytes)

    def _compile_label_ref(self,
                           label_ref: LabelRef,
                           curr_ip: int) -> List[int]:
        target_addr = self._labels[label_ref.label]
        if label_ref.relative:
            target_addr -= curr_ip

        return bytes_from_value(endianness=label_ref.endianness,
                                value=target_addr,
                                char_bit=self._char_bit,
                                num_bytes=label_ref.size_bytes)

    def _compile(self) -> Bytecode:
        """
        Converts intermediate representation to bytecode.
        """

        curr_ip = 0 # instruction pointer value at the point of running current op
        curr_op = None
        bytecode = Bytecode(self._char_bit)

        for elem in self._intermediate:
            if isinstance(elem, Operation):
                curr_op = elem
                curr_ip = len(bytecode) + curr_op.size_bytes
                bytecode.append(curr_op.opcode)
            elif isinstance(elem, Assembler.Immediate):
                bytecode += self._compile_immediate(elem)
            elif isinstance(elem, Assembler.RegisterRef):
                bytecode += self._compile_register_ref(elem)
            elif isinstance(elem, Assembler.LabelRef):
                bytecode += self._compile_label_ref(elem, curr_ip)
            else:
                raise AssertionError('unhandled IR type: %s' % type(elem).__name__)

        return bytecode

    def assemble(self,
                 source: str) -> Bytecode:
        """
        Turns SOURCE into compiled form.
        """
        self._reset()

        instructions = (l.strip() for l in source.strip().split('\n'))
        instructions = (i for i in instructions if i)
        for instr in instructions:
            if instr.endswith(':'):
                self._labels[instr[:-1]] = self._curr_offset
            else:
                self._append_instruction(instr)

        bytecode = self._compile()

        logging.debug(source)
        logging.debug('bytecode:\n%s',
                      make_bytes_dump(bytecode, bytecode.char_bit, alignment=4))

        return bytecode
