"""
Utility functions that do not fit elsewhere.
"""

from typing import Sequence, Optional, List, T

def group(seq: Sequence[T],
          size: int,
          fill: Optional[T] = None) -> Sequence[T]:
    """
    Splits SEQ into SIZE-tuples.

    If SIZE does not evenly divide len(SEQ):
    - If FILL is None, the last (incomplete) tuple is omitted from the result.
    - If FILL is not None, the missing elements of last tuple are set to FILL.
    """
    if fill is not None:
        seq = list(seq) + [fill] * (size - 1)
    return zip(*[iter(seq)] * size)

def make_bytes_dump(data: List[int],
                    char_bit: int,
                    alignment: int,
                    line_length: int = 80):
    """
    Converts DATA to a human-readable, hexdump-like string.
    * Each DATA element is printed in hex form, zero-padded to the maximum text
      length of a number with CHAR_BIT bits, and separated from other ones by a
      single space,
    * Groups of ALIGNMENT elements are separated by an extra space,
    * Each line contains as much groups as possible without exceeding LINE_LENGTH.
    """
    byte_str_len = len('%x' % (2**char_bit - 1))
    words_per_line = (line_length - 10) // ((alignment * (byte_str_len + 1)) + 1)
    byte_fmt = '%%0%dx' % byte_str_len

    word_groups = group(data, alignment, fill=0)
    line_groups = group(word_groups, words_per_line, fill=tuple([0] * alignment))

    lines = ('  '.join(' '.join((byte_fmt % b) for b in w) for w in wg) for wg in line_groups)
    lines_with_offsets = ('%08x  %s' % (idx * words_per_line * alignment, line)
                          for idx, line in enumerate(lines))
    return '\n'.join(lines_with_offsets)
