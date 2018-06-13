#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import enum
import typing
import logging
import sys
import collections
import os

from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value, value_from_bytes


class Register(enum.Enum):
    IP = enum.auto() # instruction pointer
    SP = enum.auto() # stack pointer
    A = enum.auto()  # accumulator
    C = enum.auto()  # counter
    F = enum.auto()  # flags

    @classmethod
    def all(cls):
        return cls._member_map_.values()

    @classmethod
    def by_name(cls, name: str) -> 'Register':
        return cls._member_map_[name]


class Flag(enum.IntFlag):
    Zero = enum.auto()
    Greater = enum.auto()


class RegisterSet:
    def __init__(self):
        self.reset()

    def reset(self):
        self._registers = {r: 0 for r in Register.all()}

    def __getitem__(self, reg: Register) -> int:
        try:
            return self._registers.get(reg)
        except KeyError as e:
            raise KeyError('unknown register: %s' % reg) from e

    def __setitem__(self, reg: Register, val: int):
        assert reg in self._registers
        try:
            self._registers[reg] = val
        except KeyError as e:
            raise KeyError('unknown register: %s' % reg) from e

    def __getattr__(self, name: str) -> int:
        return self.__getitem__(Register.by_name(name))

    def __setattr__(self, name: str, val: int):
        try:
            return self.__setitem__(Register.by_name(name), val)
        except KeyError:
            try:
                return super().__setattr__(name, val)
            except KeyError:
                pass
            raise

    def __str__(self) -> str:
        return '\n'.join('%s = %d (%x)' % (n, v, v) for n, v in self._registers.items())


class UnalignedMemoryAccessError(Exception):
    def __init__(self, address: int, alignment: int):
        super().__init__('Address %#x is not %d-byte aligned' % (address, alignment))


class Memory:
    def __init__(self,
                 size: int = None,
                 value: typing.List[int] = None,
                 char_bit: int = 8,
                 alignment: int = 1):
        self._char_bit = char_bit
        self._alignment = alignment

        if not size:
            self._memory = value
        else:
            self._memory = ([0] * size)
            if value:
                for idx, byte in enumerate(value):
                    if byte >= 2**char_bit:
                        raise ValueError('byte %d at offset %d is larger than the limit imposed '
                                         'by given char_bit = %d' % (byte, idx, char_bit))
                self._memory[:len(value)] = value

    @property
    def char_bit(self) -> int:
        return self._char_bit

    @property
    def alignment(self) -> int:
        return self._alignment

    def __len__(self):
        return len(self._memory)

    def __getitem__(self,
                    addr: int) -> int:
        try:
            return self._memory[addr]
        except IndexError as e:
            raise IndexError('invalid memory access at address %d' % addr) from e

    def __setitem__(self,
                    addr: int,
                    val: int):
        assert val < 2**self.char_bit
        try:
            self._memory[addr] = val
        except IndexError as e:
            raise IndexError('invalid memory access at address %d' % addr) from e

    def get_multibyte(self,
                      addr: int,
                      size_bytes: int,
                      endianness: Endianness = Endianness.Big) -> int:
        if addr % self.alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=self.alignment)

        return value_from_bytes(endianness=endianness,
                                val_bytes=self._memory[addr:addr+size_bytes],
                                char_bit=self.char_bit)

    def set_multibyte(self,
                      addr: int,
                      value: int,
                      size_bytes: int,
                      endianness: Endianness = Endianness.Big):
        if addr % self.alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=self.alignment)
        assert value < 2**(size_bytes * self.char_bit)

        self._memory[addr:addr+size_bytes] = bytes_from_value(endianness=endianness,
                                                              value=value,
                                                              char_bit=self.char_bit,
                                                              num_bytes=size_bytes)

    def __str__(self):
        return make_bytes_dump(self._memory, self.char_bit, self.alignment)


class Packer:
    class Packable(typing.NamedTuple):
        name: str
        size_bytes: int
        decode: typing.Callable[[Endianness, typing.List[int], int], int] = value_from_bytes
        encode: typing.Callable[[Endianness, int, int, int], typing.List[int]] = bytes_from_value

    _values = {p.name: p for p in [
        Packable(name='b', size_bytes=1),
        Packable(name='r', size_bytes=1), # register index
        Packable(name='a', size_bytes=5),
        Packable(name='w', size_bytes=7),
    ]}

    @classmethod
    def calcsize(cls, fmt: str):
        return sum(cls._values[c].size_bytes for c in fmt)

    @classmethod
    def unpack(cls,
               endianness: Endianness,
               char_bit: int,
               fmt: str,
               data: typing.List[int]):
        result = []
        for c in fmt:
            try:
                packable = cls._values[c]
            except KeyError as e:
                raise KeyError('unknown data size specified: %s' % c) from e

            assert len(data) > 0
            result.append(packable.decode(endianness=endianness,
                                          val_bytes=data[:packable.size_bytes],
                                          char_bit=char_bit))
            data = data[packable.size_bytes:]

        assert len(data) == 0
        return result

    @classmethod
    def pack(cls,
             endianness: Endianness,
             char_bit: int,
             fmt: str,
             args: typing.List[int]):
        assert len(fmt) == len(args)

        result = []
        for c, arg in zip(fmt, args):
            try:
                packable = cls._values[c]
            except KeyError as e:
                raise KeyError('unknown data size specified: %s' % c) from e

            result += packable.encode(endianness=endianness,
                                      value=arg,
                                      char_bit=char_bit,
                                      num_bytes=packable.size_bytes)

        return result


class Operation:
    _opcode_counter = 0

    def __init__(self, arg_def: str = ''):
        self.arg_def = arg_def

        self.opcode = Operation._opcode_counter
        Operation._opcode_counter += 1

        self.mnemonic = None
        self.operation = None

    @property
    def size_bytes(self) -> int:
        return 1 + self.args_size

    @property
    def args_size(self) -> int:
        return Packer.calcsize(self.arg_def)

    @property
    def args_endianness(self) -> Endianness:
        return Endianness.Little if self.opcode % 2 else Endianness.Big

    def decode_args(self,
                    char_bit: int,
                    memory: typing.List[int]):
        return Packer.unpack(self.args_endianness, char_bit, self.arg_def, memory)

    def encode_args(self,
                    char_bit: int,
                    args: typing.List[int]) -> typing.List[int]:
        return Packer.pack(self.args_endianness, char_bit, self.arg_def, args)

    def run(self, cpu: 'CPU', *args, **kwargs):
        return self.operation(cpu, *args, **kwargs)

    def __call__(self, wrapped: typing.Callable):
        self.operation = wrapped
        self.mnemonic = wrapped.__name__.replace('_', '.')
        return self

class HaltRequested(Exception): pass

class CPU:
    class Operations:
        @Operation(arg_def='rr')
        def movw_r2r(cpu: 'CPU', dst_reg: int, src_reg: int):
            cpu.registers[Register(dst_reg)] = cpu.registers[Register(src_reg)]

        @Operation(arg_def='rb')
        def movb_i2r(cpu: 'CPU', reg: int, immb: int):
            cpu.registers[Register(reg)] = immb

        @Operation(arg_def='ra')
        def movb_m2r(cpu: 'CPU', reg: int, addr: int):
            cpu.registers[Register(reg)] = cpu.ram[addr]

        @Operation(arg_def='ar')
        def movb_r2m(cpu: 'CPU', addr: int, reg: int):
            cpu.ram[addr] = cpu.registers[Register(reg)]

        @Operation(arg_def='rw')
        def movw_i2r(cpu: 'CPU', reg: int, immw: int):
            cpu.registers[Register(reg)] = immw

        @Operation(arg_def='ra')
        def movw_m2r(cpu: 'CPU', reg: int, addr: int):
            cpu.registers[Register(reg)] = \
                    cpu.ram.get_multibyte(addr, size_bytes=Packer.calcsize('w'))

        @Operation(arg_def='ar')
        def movw_r2m(cpu: 'CPU', addr: int, reg: int):
            cpu.ram.set_multibyte(addr,
                                  cpu.registers[Register(reg)],
                                  size_bytes=Packer.calcsize('w'))

        @Operation(arg_def='rr')
        def ldb_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
            cpu.registers[Register(dst_reg)] = cpu.ram[cpu.registers[Register(addr_reg)]]
            cpu._set_flags(cpu.registers[Register(dst_reg)])

        @Operation(arg_def='rr')
        def ldw_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
            cpu.registers[Register(reg)] = \
                    cpu.ram.get_multibyte(cpu.registers[Register(addr_reg)],
                                          size_bytes=Packer.calcsize('w'))
            cpu._set_flags(cpu.registers[Register(dst_reg)])

        @Operation(arg_def='a')
        def jmp_rel(cpu: 'CPU', addr: int):
            cpu.registers.IP += addr

        @Operation()
        def out(cpu: 'CPU'):
            sys.stdout.write(chr(cpu.registers.A))

        @Operation(arg_def='a')
        def call_rel(cpu: 'CPU', addr: int):
            addr_size = Packer.calcsize('a')
            cpu.registers.SP -= addr_size
            cpu.stack.set_multibyte(cpu.registers.SP,
                                    cpu.registers.IP,
                                    size_bytes=addr_size)
            cpu.registers.IP += addr

        @Operation()
        def ret(cpu: 'CPU'):
            addr_size = Packer.calcsize('a')
            cpu.registers.IP = cpu.stack.get_multibyte(cpu.registers.SP,
                                                       size_bytes=addr_size)

        @Operation(arg_def='rb')
        def add_b(cpu: 'CPU', reg: int, immb: int):
            cpu.registers[Register(reg)] += immb
            cpu._set_flags(cpu.registers[Register(reg)])

        @Operation(arg_def='rw')
        def add_w(cpu: 'CPU', reg: int, immw: int):
            cpu.registers[Register(reg)] += immw
            cpu._set_flags(cpu.registers[Register(reg)])

        @Operation(arg_def='rb')
        def sub_b(cpu: 'CPU', reg: int, immb: int):
            cpu.registers[Register(reg)] -= immb
            cpu._set_flags(cpu.registers[Register(reg)])

        @Operation(arg_def='rb')
        def sub_w(cpu: 'CPU', reg: int, immw: int):
            cpu.registers[Register(reg)] -= immw
            cpu._set_flags(cpu.registers[Register(reg)])

        @Operation(arg_def='rw')
        def cmp_w(cpu: 'CPU', reg: int, immw: int):
            cpu._set_flags(cpu.registers[Register(reg)] - immw)

        @Operation(arg_def='rr')
        def cmp_r(cpu: 'CPU', reg_a: int, reg_b: int):
            cpu._set_flags(cpu.registers[Register(reg_a)] - cpu.registers[Register(reg_b)])

        @Operation(arg_def='a')
        def je_rel(cpu: 'CPU', addr: int):
            if cpu.registers.F & Flag.Zero:
                cpu.registers.IP += addr

        @Operation(arg_def='a')
        def ja_rel(cpu: 'CPU', addr: int):
            if cpu.registers.F & Flag.Greater:
                cpu.registers.IP += addr

        @Operation(arg_def='a')
        def jae_rel(cpu: 'CPU', addr: int):
            if cpu.registers.F & (Flag.Equal | Flag.Greater):
                cpu.registers.IP += addr

        @Operation(arg_def='a')
        def jb_rel(cpu: 'CPU', addr: int):
            if not (cpu.registers.F & (Flag.Equal | Flag.Greater)):
                cpu.registers.IP += addr

        @Operation(arg_def='a')
        def jbe_rel(cpu: 'CPU', addr: int):
            if not (cpu.registers.F & Flag.Greater):
                cpu.registers.IP += addr

        @Operation()
        def halt(cpu: 'CPU'):
            raise HaltRequested()


    OPERATIONS_BY_OPCODE = {o.opcode: o for o in Operations.__dict__.values() if isinstance(o, Operation)}
    OPERATIONS_BY_MNEMONIC = {o.mnemonic: o for o in Operations.__dict__.values() if isinstance(o, Operation)}

    def __init__(self):
        self.registers = RegisterSet()

        self.flash = None
        self.ram = None
        self.stack = None

    def _set_flags(self, value: int):
        self.registers.F = (Flag.Zero & (value == 0)
                            | Flag.Greater & (value > 0))
        logging.debug('set_flags: %d; F = %d' % (value, self.registers.F))

    def execute(self,
                program: Memory,
                ram: Memory,
                stack: Memory):
        self.registers.IP = 0
        self.registers.SP = len(stack)

        self.program = program
        self.ram = ram
        self.stack = stack

        try:
            while True:
                idx = self.registers.IP

                try:
                    op = self.OPERATIONS_BY_OPCODE[program[idx]]
                except KeyError as e:
                    raise KeyError('invalid opcode: %d (%x) at address %08x'
                                   % (program[idx], program[idx], idx)) from e

                op_bytes = program[idx:idx+op.size_bytes]
                args = op.decode_args(char_bit=program.char_bit,
                                      memory=op_bytes[1:])
                self.registers.IP = idx + op.size_bytes

                logging.debug('%08x: %-8s %-20s %s' % (idx, op.mnemonic, ', '.join(str(x) for x in args), ' '.join('%03x' % b for b in op_bytes)))
                op.run(self, *args)
        except HaltRequested:
            pass

    def __str__(self):
        return ('--- REGISTERS ---\n'
                '%s\n'
                '--- PROGRAM ---\n'
                '%s\n'
                '--- RAM ---\n'
                '%s\n'
                '--- STACK ---\n'
                '%s\n' % (self.registers, self.program, self.ram, self.stack))


def asm_compile(text: str, char_bit: int) -> typing.List[int]:
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

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'))

data = Memory(char_bit=9, alignment=7, value=b'Hello World!', size=128)
stack = Memory(char_bit=9, alignment=5, size=5*32)
program = Memory(char_bit=9, alignment=1, value=asm_compile(sys.stdin.read(), char_bit=9))

try:
    cpu = CPU()
    cpu.execute(program=program, ram=data, stack=stack)
finally:
    logging.debug(cpu)
