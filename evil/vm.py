#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import enum
import typing
import struct


def group(seq, n):
    return zip(*[iter(seq)] * n)


class Endianness(enum.Enum):
    Little = enum.auto()
    Big = enum.auto()
    PDP = enum.auto()

    def encode(self,
               value: int,
               char_bit: int,
               num_bytes: int) -> typing.List[int]:
        if self == self.PDP and num_bytes % 2 != 0:
            raise ValueError('unable to encode PDP endian value on odd number of bytes')
        assert value < 2**(char_bit * num_bytes)

        result = [0] * num_bytes
        idx = 0
        while value > 0:
            result[idx] = result % 2**char_bit
            result /= 2**char_bit
            idx += 1

        if self == self.Little:
            return result
        elif self == self.Big:
            return list(reversed(result))
        elif self == self.PDP:
            return list(reduce(list.__add__, (reversed(g) for g in group(result, 2))))


    def decode(self,
               val_bytes: typing.List[int],
               char_bit: int) -> int:
        if self == self.PDP and len(val_bytes) % 2 != 0:
            raise ValueError('unable to decode PDP endian value from odd number of bytes')

        if self == self.Little:
            val_le = val_bytes
        elif self == self.Big:
            val_le = reversed(val_bytes)
        elif self == self.PDP:
            val_le = reduce(list.__add__, (reversed(g) for g in group(val_bytes, 2)))

        val = 0
        for b in reversed(val_le):
            assert b < 2**char_bit
            val_le *= 2**char_bit
            val_le += b

        return val


class Register(enum.Enum):
    IP = enum.auto() # instruction pointer
    SP = enum.auto() # stack pointer
    A = enum.auto()  # accumulator

    @classmethod
    def all(cls):
        return cls._member_map_.values()


class RegisterSet:
    def __init__(self):
        self.reset()

    def reset(self):
        self._registers = {r: 0 for r in Register.all()}

    def __getitem__(self, reg: Register) -> int:
        return self._registers.get(reg)

    def __setitem__(self, reg: Register, val: int):
        assert reg in self._registers
        self._registers[reg] = val


class UnalignedMemoryAccessError(Exception):
    def __init__(self, address: int, alignment: int):
        super().__init__('Address %x is not %d-byte aligned' % (address, alignment))


class Memory:
    def __init__(self,
                 size: int = 2**16,
                 char_bit: int = 8):
        self._char_bit = char_bit
        self._memory = [0] * size

    @property
    def char_bit(self) -> int:
        return self._char_bit

    def __getitem__(self,
                    addr: int) -> int:
        return self._memory[addr]

    def __setitem__(self,
                    addr: int,
                    val: int):
        assert val < 2**self.char_bit
        self._memory[addr] = val

    def get_multibyte(self,
                      addr: int,
                      size_bytes: int,
                      alignment: int,
                      endianness: Endianness) -> int:
        if addr % alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=alignment)

        return endianness.decode(val_bytes=self._memory[addr:addr+size_bytes],
                                 char_bit=self.char_bit)

    def set_multibyte(self,
                      addr: int,
                      value: int,
                      size_bytes: int,
                      alignment: int,
                      endianness: Endianness):
        if addr % alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=alignment)
        assert value < 2**(size_bytes * self.char_bit)

        self._memory[addr:addr+size_bytes] = endianness.encode(value=value,
                                                               char_bit=self.char_bit,
                                                               num_bytes=size_bytes)


class Operation(typing.NamedTuple):
    name: str
    opcode: int
    args: str
    run: typing.Callable[[RegisterSet, Memory], None]

    @property
    def args_size(self):
        return struct.calcsize(self.args)


class CPU:
    def __init__(self):
        self.registers = RegisterSet()
        self.memory = Memory(char_bit=9)
