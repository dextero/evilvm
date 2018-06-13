#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import logging
import sys
import os

from evil.cpu import CPU
from evil.memory import Memory
from evil.assembler import Assembler

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'))

asm = Assembler(char_bit=9)

data = Memory(char_bit=9, alignment=7, value=b'Hello World!', size=128)
stack = Memory(char_bit=9, alignment=5, size=5*32)
program = Memory(char_bit=9, alignment=1, value=asm.assemble(sys.stdin.read()))

try:
    cpu = CPU()
    cpu.execute(program=program, ram=data, stack=stack)
finally:
    logging.debug(cpu)
