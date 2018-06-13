import collections
import logging
from typing import List

from evil.vm import CPU, Packer, Register, Operation
from evil.utils import make_bytes_dump

def asm_compile(text: str, char_bit: int) -> List[int]:
    labels = {}
    label_refs = collections.defaultdict(list)

    def resolve_arg(text: str,
                    op_address: int,
                    arg_offset: int, # relative to op address
                    op: Operation):
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
            label_refs[text].append((op, op_address, arg_offset))
            return 0

    bytecode = []

    for line in text.strip().split('\n'):
        line = line.strip()
        if line.endswith(':'):
            labels[line[:-1]] = len(bytecode)
        elif line:
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
                args.append(resolve_arg(arg, len(bytecode), arg_off, op))
                arg_off += Packer.calcsize(op.arg_def[idx]) 

            op_bytecode += op.encode_args(char_bit=char_bit, args=args)

            logging.debug('% 9s %s' % ('', line))
            logging.debug('%08x: %-8s %-20s %s' % (len(bytecode), op.mnemonic, ', '.join(str(x) for x in args), ' '.join('%03x' % b for b in op_bytecode)))
            bytecode += op_bytecode

    for label, refs in label_refs.items():
        for op, op_address, arg_offset in refs:
            target_addr = labels[label]
            fill_addr = op_address + arg_offset

            needs_relative_addr = op.mnemonic.endswith('.rel')
            if needs_relative_addr:
                # At the point of executing OP, IP points to the next instruction
                target_addr = target_addr - (op_address + op.size_bytes)

            logging.debug('filling address @ %#010x with %#010x (%s, %s)'
                          % (fill_addr, target_addr, label, 'relative' if needs_relative_addr else 'absolute'))

            packed_addr = Packer.pack(endianness=op.args_endianness,
                                      char_bit=char_bit,
                                      fmt='a',
                                      args=[target_addr])
            bytecode[fill_addr:fill_addr+Packer.calcsize('a')] = packed_addr

    logging.debug(text)
    logging.debug('bytecode:\n' + make_bytes_dump(bytecode, char_bit, alignment=4))

    return bytecode

