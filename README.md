Evil VM
=======

A simple generic virtual machine for a made-up architecture.

This is *very much* work-in-progress. Expect stuff to break in unexpected ways.


Requirements
============

* Python 3.6+
* Linux OS


Usage
=====

    # run a simple Hello World
    python3 -m evil asm/hello.asm

    # also print some fancy logs
    LOGLEVEL=DEBUG python3 -m evil asm/hello.asm

    # run a crude snake-like game in the terminal
    # NOTE: requires char_bit >= 8, word_size * char_bit >= 12, addr_size * char_bit >= 12
    python3 -m evil asm/snek.asm --ram-size 1024
    python3 -m evil asm/snek.asm --ram-size 1024 --char-bit 12 --word-size 1 --addr-size 1

    # make the VM use some more familiar settings
    python3 -m evil asm/hello.asm --char-bit 8 --word-size 4 --addr-size 4 --map-memory ram=program stack=program

    # display help message
    python3 -m evil --help


Features
========

* Built-in assembler!
* 9 bits per byte! (configurable)
* 7 bytes per machine word! (configurable)
* 5 bytes per memory address! (configurable)
* 3 logically separate address spaces (but nothing prevents one from mapping all to a single memory area):

  * RAM area
  * code (read-only)
  * call stack (only accessible through call/ret instructions)

* Endianness used for encoding operation arguments depends on opcode parity!


Registers
=========

See ``Register`` class in ``evil/cpu.py``.


Instruction set
===============

See ``Operations`` class methods in ``evil/cpu.py``.
