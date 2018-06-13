from typing import List, NamedTuple, Any, Union

from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value, value_from_bytes


class DataType(NamedTuple):
    name: str
    size_bytes: int
    alignment: int

    _TYPES = {}

    @classmethod
    def from_fmt(cls, fmt_c: str):
        try:
            return cls._TYPES[fmt_c]
        except KeyError as err:
            raise KeyError('invalid data format specifier: %s' % fmt_c) from err

    @classmethod
    def calcsize(cls, fmt: str):
        """
        Returns number of bytes occupied by arguments described by given FMT.
        """
        return sum(cls._TYPES[c].size_bytes for c in fmt)

DataType._TYPES = {p.name: p for p in [
    DataType(name='b', size_bytes=1, alignment=1),
    DataType(name='r', size_bytes=1, alignment=1), # register index
    DataType(name='a', size_bytes=5, alignment=5),
    DataType(name='w', size_bytes=7, alignment=7),
]}


class Memory:
    def __init__(self,
                 char_bit: int,
                 size: int = None,
                 value: List[int] = None):
        self._char_bit = char_bit

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

    def _get_datatype(self,
                      addr: int,
                      datatype: DataType,
                      endianness: Endianness) -> int:
        return value_from_bytes(endianness=endianness,
                                val_bytes=self._memory[addr:addr+datatype.size_bytes],
                                char_bit=self.char_bit)

    def _set_datatype(self,
                      addr: int,
                      value: int,
                      datatype: DataType,
                      endianness: Endianness):
        self._memory[addr:addr+datatype.size_bytes] = \
                bytes_from_value(endianness=endianness,
                                 value=value,
                                 char_bit=self.char_bit,
                                 num_bytes=datatype.size_bytes)

    def get_fmt(self,
                fmt: str,
                addr: int,
                endianness: Endianness = Endianness.Big) -> List[Any]:
        """
        Decodes arguments from the memory starting at ADDR, based on FMT specifier.
        """
        result = []
        for fmt_c in fmt:
            datatype = DataType.from_fmt(fmt_c)
            result.append(self._get_datatype(addr, datatype, endianness))
            addr += datatype.size_bytes

        return result

    def set_fmt(self,
                fmt: str,
                addr: int,
                args: Union[int, List[int]],
                endianness: Endianness = Endianness.Big):
        if isinstance(args, int):
            args = [args]

        assert len(fmt) == len(args)

        for fmt_c, arg in zip(fmt, args):
            datatype = DataType.from_fmt(fmt_c)
            self._set_datatype(addr, arg, datatype, endianness)
            addr += datatype.size_bytes

    def __str__(self):
        return make_bytes_dump(self._memory,
                               self.char_bit,
                               DataType.from_fmt('w').alignment)


class UnalignedMemoryAccessError(Exception):
    def __init__(self, address: int, alignment: int):
        super().__init__('Address %#x is not %d-byte aligned' % (address, alignment))


class StrictlyAlignedMemory(Memory):
    def _get_datatype(self,
                      addr: int,
                      datatype: DataType,
                      endianness: Endianness) -> int:
        if addr % datatype.alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=datatype.alignment)

        return super()._get_datatype(addr, datatype, endianness)

    def _set_datatype(self,
                      addr: int,
                      value: int,
                      datatype: DataType,
                      endianness: Endianness):
        if addr % datatype.alignment != 0:
            raise UnalignedMemoryAccessError(address=addr, alignment=datatype.alignment)

        return super()._set_datatype(addr, value, datatype, endianness)


class ExtendableMemory(Memory):
    def __init__(self, char_bit: int):
        super().__init__(char_bit=char_bit,
                         value=[])

    def _resize_if_required(self, desired_size: int):
        if len(self) < desired_size:
            self._memory += [0] * (desired_size - len(self))

    def __setitem__(self, addr: int, val: int):
        self._resize_if_required(addr + 1)
        super().__setitem__(addr, val)

    def _set_datatype(self,
                      addr: int,
                      value: int,
                      datatype: DataType,
                      endianness: Endianness):
        self._resize_if_required(addr + datatype.size_bytes)
        super()._set_datatype(addr, value, datatype, endianness)

    def append(self,
               value: int,
               datatype: DataType,
               endianness: Endianness):
        return self._set_datatype(len(self), value, datatype, endianness)

    def freeze(self) -> Memory:
        frozen = Memory(self.char_bit, value=self._memory)
        self.value = []
        return frozen
