"""
Utility functions that do not fit elsewhere.
"""

import itertools
import string
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
                    line_length: int = 80,
                    address_base: int = 0):
    """
    Converts DATA to a human-readable, hexdump-like string.
    * Each DATA element is printed in hex form, zero-padded to the maximum text
      length of a number with CHAR_BIT bits, and separated from other ones by a
      single space,
    * Groups of ALIGNMENT elements are separated by an extra space,
    * Each line contains as much groups as possible without exceeding LINE_LENGTH.
    """
    byte_str_len = len('%x' % (2**char_bit - 1))
    words_per_line = ((line_length
                       - 10 # 10 bytes for address on the left
                       - 2) # 2 bytes for space between hex digits and right column
                      // ((alignment * (byte_str_len # byte size
                                        + 1 # 1 space between each byte
                                        + 1)) # 1 character on the right column per byte
                           + 1 # 1 extra space between words in hex dump
                           + 1)) # 1 more in the right column
    byte_fmt = '%%0%dx' % byte_str_len

    word_groups = group(data, alignment, fill=0)
    line_groups = list(group(word_groups, words_per_line, fill=tuple([0] * alignment)))

    def to_printable(c: int):
        if (c < 128
                and chr(c) in string.printable
                and chr(c) not in string.whitespace):
            return chr(c)
        return '.'

    lines = ('  '.join(' '.join((byte_fmt % b) for b in w) for w in wg) for wg in line_groups)
    printable_lines = (' '.join(''.join(to_printable(b) for b in w) for w in wg) for wg in line_groups)

    lines_with_offsets = ('%08x  %s  %s' % (address_base + idx * words_per_line * alignment, line, printable)
                          for idx, (line, printable) in enumerate(zip(lines, printable_lines)))
    return '\n'.join(lines_with_offsets)


def tokenize(text: str) -> List[str]:
    IDENTIFIER_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits + '_.'

    def parse_escape(text: str):
        if not text:
            return 0
        if text[0] == 'x':
            return 1 + parse_while_matches(text[1:], string.hexdigits)
        return 1

    def parse_quote(text: str, quote_char: str):
        idx = 0
        quote = ''
        while idx < len(text):
            size = 1
            if text[idx] == '\\':
                size += parse_escape(text[1:])
                quote += text[idx:idx+size]
            elif text[idx] == quote_char:
                return quote + text[idx:idx+size], idx + size
            else:
                quote += text[idx]
            idx += size

        return quote, len(text)

    def parse_while_matches(text: str, valid: str):
        return len(list((itertools.takewhile(lambda c: c in valid, text))))

    def parse_punctuation(text: str):
        multichar_operators  = { '>>', '<<' }

        for op in multichar_operators:
            if text.startswith(op):
                return op, len(op)

        return text[0], 1

    result = []
    idx = 0
    while idx < len(text):
        size = 1
        if text[idx] in ('"', "'"):
            tok, tok_size = parse_quote(text[idx+1:], text[idx])
            size += tok_size
            result.append(text[idx] + tok)
        elif text[idx] in string.punctuation:
            tok, tok_size = parse_punctuation(text[idx:])
            size = tok_size
            result.append(tok)
        elif text[idx] in IDENTIFIER_CHARS:
            size += parse_while_matches(text[idx+1:], IDENTIFIER_CHARS)
            result.append(text[idx:idx+size])
        elif text[idx].isspace():
            size += parse_while_matches(text[idx+1:], string.whitespace)
        else:
            raise ValueError('ಠ_ಠ: %s', text[idx])
        idx += size

    return result
