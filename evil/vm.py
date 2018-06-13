#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import logging
import sys
import os
import argparse

from evil.cpu import CPU
from evil.memory import Memory, DataType
from evil.assembler import Assembler

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'))

MEMORY_BLOCKS = {}

parser = argparse.ArgumentParser(description='''
Run a program within the Evil VM.

Recognized environment variables:
- LOGLEVEL - log level to use. Default is INFO; DEBUG may print some interesting stuff.
''')
parser.add_argument(dest='source',
                    nargs=1,
                    default='/dev/stdin',
                    help='Assembly source file to load and execute')
parser.add_argument('-p', '--program-size',
                    default=None,
                    type=int,
                    help='Size, in bytes, of the program address space. If not specified, program memory space will be just large enough to accomodate program bytecode')
parser.add_argument('-r', '--ram-size',
                    default=128,
                    type=int,
                    help='Size, in machine-words, of the RAM address space')
parser.add_argument('-s', '--stack-size',
                    default=32,
                    type=str,
                    help='Size, in address-words, of the return stack address space')
parser.add_argument('-m', '--map-memory',
                    nargs='+',
                    type=str,
                    default=[],
                    help='Remap address spaces. E.g. ram=program will cause RAM to use program address space. Available: program, ram, stack')
parser.add_argument('-b', '--char-bit',
                    type=int,
                    default=9,
                    help='Number of bits per byte.')

args = parser.parse_args()

with open(args.source[0]) as infile:
    asm = Assembler(char_bit=args.char_bit)
    if args.program_size is None:
        MEMORY_BLOCKS['program'] = asm.assemble_to_memory(infile.read())
    else:
        MEMORY_BLOCKS['program'] = Memory(char_bit=args.char_bit,
                                          value=asm.assemble(infile.read()))

MEMORY_BLOCKS['ram'] = Memory(char_bit=args.char_bit, size=DataType.calcsize('w') * args.ram_size)
MEMORY_BLOCKS['stack'] = Memory(char_bit=args.char_bit, size=DataType.calcsize('a') * args.stack_size)

for mapping in args.map_memory:
    dst, src = mapping.split('=', maxsplit=1)
    if src not in MEMORY_BLOCKS or dst not in MEMORY_BLOCKS:
        raise ValueError('invalid memory mapping: %s' % mapping)

    MEMORY_BLOCKS[dst] = MEMORY_BLOCKS[src]

try:
    cpu = CPU()
    cpu.execute(program=MEMORY_BLOCKS['program'],
                ram=MEMORY_BLOCKS['ram'],
                stack=MEMORY_BLOCKS['stack'])
finally:
    logging.debug(cpu)
