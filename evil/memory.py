from typing import List, NamedTuple, Any, Tuple

from evil.utils import make_bytes_dump
from evil.endianness import Endianness, bytes_from_value, value_from_bytes
from evil.fault import Fault


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

class MemoryAccessFault(Fault):
    def __init__(self,
                 addr: int,
                 valid_begin: int,
                 valid_end: int):
        super().__init__('Invalid memory access - address %d is not in range [%d, %d)'
                         % (addr, valid_begin, valid_end))

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
        except IndexError as err:
            raise MemoryAccessFault(addr, 0, len(self)) from err

    def __setitem__(self,
                    addr: int,
                    val: int):
        assert val < 2**self.char_bit
        try:
            self._memory[addr] = val
        except IndexError as err:
            raise MemoryAccessFault(addr, 0, len(self)) from err

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

    def _get_fmt_impl(self,
                      fmt_c: str,
                      addr: int,
                      endianness: Endianness = Endianness.Big) -> Tuple[int, Any]:
        assert len(fmt_c) == 1
        datatype = DataType.from_fmt(fmt_c)
        return datatype.size_bytes, self._get_datatype(addr, datatype, endianness)

    def get_fmt(self,
                fmt: str,
                addr: int,
                endianness: Endianness = Endianness.Big) -> List[Any]:
        return self._get_fmt_impl(fmt, addr, endianness)[1]

    def get_fmt_multiple(self,
                         fmt: str,
                         addr: int,
                         endianness: Endianness = Endianness.Big) -> Any:
        result = []
        for fmt_c in fmt:
            size, elem = self._get_fmt_impl(fmt_c, addr, endianness)
            addr += size
            result.append(elem)
        return result

    def set_fmt(self,
                fmt: str,
                addr: int,
                arg: int,
                endianness: Endianness = Endianness.Big):
        assert len(fmt) == 1
        datatype = DataType.from_fmt(fmt)
        self._set_datatype(addr, arg, datatype, endianness)

    def make_dump(self, alignment):
        return make_bytes_dump(self._memory, self.char_bit, alignment)

    def __str__(self):
        return self.make_dump(DataType.from_fmt('w').alignment)


class UnalignedMemoryAccessFault(Fault):
    def __init__(self, address: int, alignment: int):
        super().__init__('Address %#x is not %d-byte aligned' % (address, alignment))


class StrictlyAlignedMemory(Memory):
    def _get_datatype(self,
                      addr: int,
                      datatype: DataType,
                      endianness: Endianness) -> int:
        if addr % datatype.alignment != 0:
            raise UnalignedMemoryAccessFault(address=addr, alignment=datatype.alignment)

        return super()._get_datatype(addr, datatype, endianness)

    def _set_datatype(self,
                      addr: int,
                      value: int,
                      datatype: DataType,
                      endianness: Endianness):
        if addr % datatype.alignment != 0:
            raise UnalignedMemoryAccessFault(address=addr, alignment=datatype.alignment)

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
