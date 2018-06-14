"""
Functions for encoding/decoding values preserving endianness.
"""

import enum
from typing import List
from functools import reduce

from evil.utils import group


class Endianness(enum.Enum):
    """
    Byte ordering used when saving a value to memory.
    """
    Little = enum.auto()
    Big = enum.auto()
    PDP = enum.auto()

def bytes_from_value(endianness: Endianness,
                     value: int,
                     char_bit: int,
                     num_bytes: int) -> List[int]:
    """
    Encodes VALUE into a list of NUM_BYTES bytes, each CHAR_BIT-bit long using
    sign-magnitude encoding.
    The order of bytes depends on ENDIANNESS.
    """
    if endianness == Endianness.PDP and num_bytes % 2 != 0:
        raise ValueError('unable to encode PDP endian value on odd number of bytes')
    assert value < 2**(char_bit * num_bytes)

    negative = False
    if value < 0:
        negative = True
        value = -value

    result = [0] * num_bytes
    idx = 0
    while value > 0:
        try:
            result[idx] = value % 2**char_bit
        except IndexError as err:
            raise ValueError('value (%d) too long to encode on %d %d-bit bytes'
                             % (value, num_bytes, char_bit)) from err
        value //= 2**char_bit
        idx += 1

    if negative:
        msb = (1 << (char_bit - 1))
        result[-1] |= msb

    if endianness == Endianness.Little:
        return result
    elif endianness == Endianness.Big:
        return list(reversed(result))
    elif endianness == Endianness.PDP:
        return list(reduce(list.__add__, (reversed(g) for g in group(result, 2))))
    else:
        assert False, 'Invalid endianness: %r' % endianness


def value_from_bytes(endianness: Endianness,
                     val_bytes: List[int],
                     char_bit: int) -> int:
    """
    Decodes a list of CHAR_BIT-bit wide bytes from VAL_BYTES into an integer.
    Sign-magnitude encoding is assumed.
    The order of bytes depends on ENDIANNESS.
    """
    if endianness == Endianness.PDP and len(val_bytes) % 2 != 0:
        raise ValueError('unable to decode PDP endian value from odd number of bytes')

    if endianness == Endianness.Little:
        val_le = val_bytes
    elif endianness == Endianness.Big:
        val_le = list(reversed(val_bytes))
    elif endianness == Endianness.PDP:
        val_le = reduce(list.__add__, (reversed(g) for g in group(val_bytes, 2)))
    else:
        assert False, 'Invalid endianness: %r' % endianness

    negative = False
    msb = (1 << (char_bit - 1))
    if val_le[-1] & msb:
        negative = True
        val_le[-1] &= ~msb

    val = 0
    for byte in reversed(val_le):
        if byte >= 2**char_bit:
            raise ValueError('%d is supposed to be less than 2**%d' % (byte, char_bit))
        val *= 2**char_bit
        val += byte

    return -val if negative else val
