from typing import List

from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value, value_from_bytes


class UnalignedMemoryAccessError(Exception):
    def __init__(self, address: int, alignment: int):
        super().__init__('Address %#x is not %d-byte aligned' % (address, alignment))


class Memory:
    def __init__(self,
                 size: int = None,
                 value: List[int] = None,
                 char_bit: int = 8,
                 alignment: int = 1):
        self._char_bit = char_bit
        self._alignment = alignment

        if value:
            for idx, byte in enumerate(value):
                if byte >= 2**char_bit:
                    raise ValueError('byte %d at offset %d is larger than the limit imposed '
                                     'by given char_bit = %d' % (byte, idx, char_bit))

        if not size:
            self._memory = list(value)
        else:
            self._memory = ([0] * size)
            if value:
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



class ExtendableMemory(Memory):
    def __init__(self, char_bit: int):
        super().__init__(self,
                         char_bit=char_bit,
                         alignment=1,
                         value=[])

    def _resize_if_required(self, desired_size: int):
        if len(self) < desired_size:
            self._memory += [0] * (desired_size - len(self))

    def __setitem__(self, addr: int, val: int):
        self._resize_if_required(addr + 1)
        super().__setitem__(addr, val)

    def set_multibyte(self,
                      addr: int,
                      value: int,
                      size_bytes: int,
                      endianness: Endianness = Endianness.Big):
        self._resize_if_required(addr + size_bytes)
        super().set_multibyte(addr, value, size_bytes, endianness)
