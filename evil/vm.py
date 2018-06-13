#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import logging
import sys
import os

from evil.cpu import CPU
from evil.memory import Memory
from evil.assembler import Assembler

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'))

CHAR_BIT=9

asm = Assembler(char_bit=CHAR_BIT)

data = Memory(char_bit=CHAR_BIT, value=b'Hello World!', size=128)
stack = Memory(char_bit=CHAR_BIT, size=5*32)
program = Memory(char_bit=CHAR_BIT, value=asm.assemble(sys.stdin.read()))

try:
    cpu = CPU()
    cpu.execute(program=program, ram=data, stack=stack)
finally:
    logging.debug(cpu)
