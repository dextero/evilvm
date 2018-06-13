Evil VM
=======

A simple virtual machine for a made-up architecture.

This is *very much* work-in-progress. Expect stuff to break in unexpected ways.


Usage
=====

    python3 -m evil.vm asm/hello.asm
    python3 -m evil.vm --help


Features
========

* built-in assembler
* configurable number of bits per byte - by default 9
* 7 9bytes per machine word
* 5-9byte addresses
* 3 separate address spaces:
  * RAM area
  * code (read-only)
  * call stack (only accessible through call/ret instructions)

* Endianness used for encoding opcode arguments depends on opcode parity

* Registers:
  * A - accumulator
  * C - counter
  * F - flag register
  * IP - instruction pointer
  * SP - return address stack pointer


Instruction set
===============

See ``Operations`` class methods in ``evil/cpu.py``.
