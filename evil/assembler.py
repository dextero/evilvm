import collections
import logging
from typing import List

from evil.cpu import CPU, Packer, Register, Operation
from evil.utils import make_bytes_dump
from evil.memory import ExtendableMemory

class Bytecode(list):
    def __init__(self, char_bit: int):
        super().__init__()
        self._char_bit = char_bit

    @property
    def char_bit(self):
        return self._char_bit


class Assembler:
    def __init__(self, char_bit: int):
        self._char_bit = char_bit
        self.reset()

    def reset(self):
        self._labels = {}
        self._label_refs = collections.defaultdict(list)
        self._bytecode = Bytecode(self._char_bit)

    def _resolve_arg(self,
                     text: str,
                     op: Operation,
                     op_offset: int,
                     arg_offset: int): # relative to op_offset
        try:
            return Register.by_name(text.upper()).value
        except KeyError:
            pass

        try:
            if text[0] == "'" and text[-1] == "'":
                return ord(text[1:-1])
            else:
                return int(text, 0)
        except ValueError:
            self._label_refs[text].append((op, op_offset, arg_offset))
            return 0

    def _append_instruction(self, line: str):
        if ' ' in line:
            mnemonic, argline = line.split(' ', maxsplit=1)
        else:
            mnemonic = line
            argline = ''

        try:
            op = CPU.OPERATIONS_BY_MNEMONIC[mnemonic]
        except KeyError as e:
            raise KeyError('invalid opcode: %s' % mnemonic) from e

        op_bytecode = [op.opcode]
        arg_off = len(op_bytecode)
        args = []
        for idx, arg in enumerate(argline.split()):
            arg = arg.strip(',') # TODO: UGLYYY
            args.append(self._resolve_arg(arg, op, len(self._bytecode), arg_off))
            arg_off += Packer.calcsize(op.arg_def[idx])

        op_bytecode += op.encode_args(char_bit=self._char_bit, args=args)
        self._bytecode += op_bytecode

        logging.debug('% 9s %s' % ('', line))
        logging.debug('%08x: %-8s %-20s %s' % (len(self._bytecode), op.mnemonic, ', '.join(str(x) for x in args), ' '.join('%03x' % b for b in op_bytecode)))

    def _fill_labels(self):
        for label, refs in self._label_refs.items():
            for op, op_address, arg_offset in refs:
                target_addr = self._labels[label]
                fill_addr = op_address + arg_offset

                needs_relative_addr = op.mnemonic.endswith('.rel')
                if needs_relative_addr:
                    # At the point of executing OP, IP points to the next instruction
                    target_addr = target_addr - (op_address + op.size_bytes)

                logging.debug('filling address @ %#010x with %#010x (%s, %s)'
                              % (fill_addr, target_addr, label, 'relative' if needs_relative_addr else 'absolute'))

                packed_addr = Packer.pack(endianness=op.args_endianness,
                                          char_bit=self._char_bit,
                                          fmt='a',
                                          args=[target_addr])
                self._bytecode[fill_addr:fill_addr+Packer.calcsize('a')] = packed_addr

    def assemble(self,
                 source: str) -> Bytecode:
        self.reset()

        instructions = (l.strip() for l in source.strip().split('\n'))
        instructions = (i for i in instructions if i)
        for instr in instructions:
            if instr.endswith(':'):
                self._labels[instr[:-1]] = len(self._bytecode)
            else:
                self._append_instruction(instr)

        self._fill_labels()

        logging.debug(source)
        logging.debug('bytecode:\n' + make_bytes_dump(self._bytecode,
                                                      self._bytecode.char_bit,
                                                      alignment=4))

        return self._bytecode
