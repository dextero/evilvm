"""
Assembly -> bytecode compiler and utilities.
"""
import collections
import logging
from typing import List, NamedTuple, Sequence

from evil.cpu import CPU, Register, Operation
from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value
from evil.memory import Memory, ExtendableMemory, DataType


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
      Operation or other classes defined below. During this pass, all labels
      and its positions are discovered and noted in self._labels.
    * Second pass converts intermediate representation into final bytecode,
      filling in label values if necessary.
    """

    class IRElement:
        pass

    class Immediate(NamedTuple, IRElement):
        """ Literal value. """
        value: int
        endianness: Endianness
        datatype: DataType

    class RegisterRef(NamedTuple, IRElement):
        """ CPU register reference. """
        reg: Register
        endianness: Endianness
        datatype: DataType = DataType.from_fmt('r')

    class LabelRef(NamedTuple, IRElement):
        """ Named label reference. """
        label: str
        endianness: Endianness
        relative: bool
        datatype: DataType = DataType.from_fmt('a')

    class LineIR(NamedTuple):
        source: str
        elements: List['IRElement']
        bytecode: List[int]

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
                         datatype: DataType) -> 'Assembler.Immediate':
        if len(text) == 3 and text[0] == "'" == text[-1]:
            value = ord(text[1])
        else:
            value = int(text, 0)

        return Assembler.Immediate(value=value,
                                   datatype=datatype,
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
                return self._parse_immediate(text, operation,
                                             DataType.from_fmt(arg_type))
            except ValueError:
                # label
                return Assembler.LabelRef(label=text,
                                          endianness=operation.args_endianness,
                                          relative=operation.mnemonic.endswith('.rel'))
        else:
            raise ValueError('unsupported argument type: %s' % arg_type)

    def _append_instruction(self,
                            line: str,
                            line_num: int):
        """
        Parses LINE as an instruction and appends its intermediate
        representation to self._intermediate.
        """
        stripped_line = line.strip()
        if stripped_line.endswith(':'):
            self._labels[stripped_line[:-1]] = self._curr_offset
            self._intermediate.append(Assembler.LineIR(line, elements=[], bytecode=[]))
            return

        if not stripped_line:
            self._intermediate.append(Assembler.LineIR(line, elements=[], bytecode=[]))
            return

        if ' ' in stripped_line:
            mnemonic, argline = stripped_line.split(' ', maxsplit=1)
        else:
            mnemonic = stripped_line
            argline = ''

        try:
            operation = CPU.OPERATIONS_BY_MNEMONIC[mnemonic]
        except KeyError as err:
            raise KeyError('invalid opcode: %s' % mnemonic) from err

        op_ir = [operation]
        for idx, arg in enumerate(argline.split()):
            arg = arg.strip(',') # TODO: UGLYYY
            op_ir.append(self._parse_arg(arg, operation, operation.arg_def[idx]))

        self._intermediate.append(Assembler.LineIR(line, op_ir, bytecode=[]))
        self._curr_offset += operation.size_bytes

    def _label_ref_to_address(self,
                              label_ref: LabelRef,
                              curr_ip: int) -> List[int]:
        target_addr = self._labels[label_ref.label]
        if label_ref.relative:
            target_addr -= curr_ip
        return target_addr

    def _compile(self) -> Memory:
        """
        Fills .bytecode field of IRElements in self._intermediate,
        returns memory block with whole source bytecode
        """
        curr_ip = 0 # instruction pointer value at the point of running current op
        mem = ExtendableMemory(self._char_bit)

        for line in self._intermediate:
            prev_ip = curr_ip

            for elem in line.elements:
                if isinstance(elem, Operation):
                    curr_ip = len(mem) + elem.size_bytes
                    mem.append(elem.opcode,
                               DataType.from_fmt('b'),
                               Endianness.Little)
                elif isinstance(elem, Assembler.Immediate):
                    mem.append(elem.value,
                               elem.datatype,
                               elem.endianness)
                elif isinstance(elem, Assembler.RegisterRef):
                    mem.append(elem.reg.value,
                               elem.datatype,
                               elem.endianness)
                elif isinstance(elem, Assembler.LabelRef):
                    mem.append(self._label_ref_to_address(elem, curr_ip),
                               elem.datatype,
                               elem.endianness)
                else:
                    raise AssertionError('unhandled IR type: %s' % type(elem).__name__)

            line.bytecode[:] = mem[prev_ip:]

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

        instructions = source.strip().split('\n')
        for line_num, instr in enumerate(instructions, start=1):
            self._append_instruction(instr, line_num)

        mem = self._compile()
        self._log_source()
        return mem

    def assemble(self, source: str) -> Bytecode:
        return Bytecode.from_memory(self.assemble_to_memory(source))
