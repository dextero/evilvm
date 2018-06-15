import enum
import logging
from typing import List, Any, NamedTuple, Callable
import sys

from evil.endianness import Endianness, bytes_from_value, value_from_bytes
from evil.memory import Memory, DataType
from evil.gpu import GPU
from evil.fault import Fault

class Register(enum.Enum):
    """ CPU register """
    IP = enum.auto() # instruction pointer
    SP = enum.auto() # stack pointer
    RP = enum.auto() # return address pointer
    A = enum.auto()  # accumulator
    B = enum.auto()  # general purpose
    C = enum.auto()  # counter
    F = enum.auto()  # flags

    @classmethod
    def all(cls):
        """ Returns a set of all registers """
        return cls._member_map_.values()

    @classmethod
    def by_name(cls, name: str) -> 'Register':
        """ Finds a register by its uppercase name """
        return cls._member_map_[name]


class Flag(enum.IntFlag):
    """ Possible bit flags set on the F register """
    Zero = enum.auto()
    Greater = enum.auto()


class RegisterSet:
    """ Helper class that provides easy register access """
    def __init__(self):
        self.reset()

    def reset(self):
        """ Resets value of all registers """
        self._registers = {r: 0 for r in Register.all()}

    def __getitem__(self, reg: Register) -> int:
        try:
            return self._registers.get(reg)
        except KeyError as err:
            raise KeyError('unknown register: %s' % reg) from err

    def __setitem__(self, reg: Register, val: int):
        assert reg in self._registers
        try:
            self._registers[reg] = val
        except KeyError as err:
            raise KeyError('unknown register: %s' % reg) from err

    def __getattr__(self, name: str) -> int:
        return self.__getitem__(Register.by_name(name))

    def __setattr__(self, name: str, val: int):
        try:
            return self.__setitem__(Register.by_name(name), val)
        except KeyError:
            try:
                return super().__setattr__(name, val)
            except KeyError:
                pass
            raise

    def __str__(self) -> str:
        return '\n'.join('%s = %d (%x)' % (n, v, v) for n, v in self._registers.items())


class Operation:
    """ CPU operation decorator """
    _opcode_counter = 0

    def __init__(self, arg_def: str = ''):
        self.arg_def = arg_def

        self.opcode = Operation._opcode_counter
        Operation._opcode_counter += 1

        self.mnemonic = None
        self.operation = None

    @property
    def opcode_size_bytes(self) -> int:
        return 1

    @property
    def size_bytes(self) -> int:
        """ Size (in bytes) of this operation bytecode, including arguments """
        return self.opcode_size_bytes + self.args_size

    @property
    def args_size(self) -> int:
        """ Size (in bytes) of this operation arguments, without the opcode """
        return DataType.calcsize(self.arg_def)

    @property
    def args_endianness(self) -> Endianness:
        """ Endianness used for arguments to this particular operation """
        return Endianness.Little if self.opcode % 2 else Endianness.Big

    def decode_args(self,
                    memory: Memory,
                    addr: int) -> List[Any]:
        return memory.get_fmt_multiple(self.arg_def, addr, self.args_endianness)

    def run(self, cpu: 'CPU', *args, **kwargs):
        """ Executes the wrapped operation """
        return self.operation(cpu, *args, **kwargs)

    def __call__(self, wrapped: Callable):
        self.operation = wrapped
        self.mnemonic = wrapped.__name__.replace('_', '.')
        return self

class HaltRequested(Exception):
    """ Thrown to halt CPU execution """
    pass

class Operations:
    """ Available CPU operations """

    @Operation(arg_def='rr')
    def movw_r2r(cpu: 'CPU', dst_reg: int, src_reg: int):
        """
        movw.r2r dst, src - MOVe Word, Register to Register

        dst = src
        """
        cpu.registers[Register(dst_reg)] = cpu.registers[Register(src_reg)]

    @Operation(arg_def='rb')
    def movb_i2r(cpu: 'CPU', reg: int, immb: int):
        """
        movb.i2r dst, IMM_BYTE - MOVe Byte, Immediate to Register

        dst = IMM_BYTE
        """
        cpu.registers[Register(reg)] = immb

    @Operation(arg_def='ra')
    def movb_m2r(cpu: 'CPU', reg: int, addr: int):
        """
        movb.m2r dst, IMM_ADDR - MOVe Byte, Memory to Register

        dst = byte ptr $RAM[IMM_ADDR]
        """
        cpu.registers[Register(reg)] = cpu.ram[addr]

    @Operation(arg_def='ar')
    def movb_r2m(cpu: 'CPU', addr: int, reg: int):
        """
        movb.r2m IMM_ADDR, src - MOVe Byte, Register to Memory

        byte ptr $RAM[IMM_ADDR] = src
        """
        cpu.ram[addr] = cpu.registers[Register(reg)]

    @Operation(arg_def='rw')
    def movw_i2r(cpu: 'CPU', reg: int, immw: int):
        """
        movw.i2r dst, IMM_WORD - MOVe Word, Immediate to Register

        dst = IMM_WORD
        """
        cpu.registers[Register(reg)] = immw

    @Operation(arg_def='ra')
    def movw_m2r(cpu: 'CPU', reg: int, addr: int):
        """
        movw.m2r dst, IMM_ADDR - MOVe Word, Memory to Register

        dst = word ptr $RAM[IMM_ADDR]
        """
        cpu.registers[Register(reg)] = cpu.ram.get_fmt('w', addr)

    @Operation(arg_def='ar')
    def movw_r2m(cpu: 'CPU', addr: int, reg: int):
        """
        movw.r2m IMM_ADDR, src - MOVe Word, Register to Memory

        word ptr $RAM[IMM_ADDR] = src
        """
        cpu.ram.set_fmt('w', addr, cpu.registers[Register(reg)])

    @Operation(arg_def='rr')
    def lpb_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        lpb.r dst, src - Load Program Byte, address from Register

        dst = byte ptr $PROGRAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(dst_reg)] = cpu.program[addr]
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='rr')
    def lpa_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        lda.r dst, src - Load Program Address, address from Register

        dst = addr ptr $RAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(dst_reg)] = cpu.program.get_fmt('a', addr)
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='rr')
    def lpw_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        lpw.r dst, src - Load Program Word, address from Register

        dst = word ptr $PROGRAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(reg)] = cpu.program.get_fmt('w', addr)
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='rr')
    def ldb_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        ldb.r dst, src - Load Data Byte, address from Register

        dst = byte ptr $RAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(dst_reg)] = cpu.ram[addr]
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='rr')
    def lda_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        lda.r dst, src - Load Data Address, address from Register

        dst = addr ptr $RAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(dst_reg)] = cpu.ram.get_fmt('a', addr)
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='rr')
    def ldw_r(cpu: 'CPU', dst_reg: int, addr_reg: int):
        """
        ldw.r dst, src - Load Data Word, address from Register

        dst = word ptr $RAM[src]
        """
        addr = cpu.registers[Register(addr_reg)]
        cpu.registers[Register(reg)] = cpu.ram.get_fmt('w', addr)
        cpu._set_flags(cpu.registers[Register(dst_reg)])

    @Operation(arg_def='a')
    def jmp_rel(cpu: 'CPU', addr: int):
        """
        jmp.rel IMM_ADDR_REL - unconditional JuMP, RELative

        IP += IMM_ADDR_REL
        """
        cpu.registers.IP += addr

    @Operation()
    def out(cpu: 'CPU'):
        """
        out - print character to GPU
        """
        cpu.gpu.put(cpu.registers.A)

    @Operation(arg_def='rr')
    def seek(cpu: 'CPU', x_reg: int, y_reg: int):
        """
        seek - set current GPU write pointer position to (x, y)
        """
        cpu.gpu.seek(x=cpu.registers[Register(x_reg)],
                     y=cpu.registers[Register(y_reg)])

    @Operation(arg_def='a')
    def call_rel(cpu: 'CPU', addr: int):
        """
        call.rel addr - CALL subroutine, RELative

        RP -= sizeof_addr
        addr ptr $CALL_STACK[RP] = IP
        IP = addr
        """
        addr_size = DataType.calcsize('a')
        cpu.registers.RP -= addr_size
        cpu.call_stack.set_fmt('a', cpu.registers.RP, cpu.registers.IP)
        cpu.registers.IP += addr

    @Operation(arg_def='a')
    def call_r(cpu: 'CPU', reg: int):
        """
        call.r addr - CALL subroutine, Register

        RP -= sizeof_addr
        addr ptr $CALL_STACK[RP] = IP
        IP = reg
        """
        addr_size = DataType.calcsize('a')
        cpu.registers.RP -= addr_size
        cpu.call_stack.set_fmt('a', cpu.registers.RP, cpu.registers.IP)
        cpu.registers.IP = cpu.registers[Register(reg)]

    @Operation()
    def ret(cpu: 'CPU'):
        """
        ret - RETurn from subroutine

        IP = addr ptr $CALL_STACK[RP]
        RP += sizeof_addr
        """
        addr_size = DataType.calcsize('a')
        cpu.registers.IP = cpu.call_stack.get_fmt('a', cpu.registers.RP)
        cpu.registers.RP += addr_size

    @Operation(arg_def='r')
    def push(cpu: 'CPU', reg: int):
        """
        push - PUSH register onto data stack

        SP -= sizeof_word
        word ptr $RAM[SP] = reg
        """
        cpu.registers.SP -= DataType.from_fmt('w').size_bytes
        cpu.ram.set_fmt('w', cpu.registers.SP, cpu.registers[Register(reg)])

    @Operation(arg_def='r')
    def pop(cpu: 'CPU', reg: int):
        """
        pop - POP value from data stack into register

        reg = word ptr $RAM[SP]
        SP += sizeof_word
        """
        cpu.registers[Register(reg)] = cpu.ram.get_fmt('w', cpu.registers.SP)
        cpu.registers.SP += DataType.from_fmt('w').size_bytes

    @Operation(arg_def='rb')
    def add_b(cpu: 'CPU', reg: int, immb: int):
        """
        add.b dst, IMM_BYTE - ADD Byte, immediate

        dst += IMM_BYTE
        """
        cpu.registers[Register(reg)] += immb
        cpu._set_flags(cpu.registers[Register(reg)])

    @Operation(arg_def='rw')
    def add_w(cpu: 'CPU', reg: int, immw: int):
        """
        add.w dst, IMM_WORD - ADD Word, immediate

        dst += IMM_WORD
        """
        cpu.registers[Register(reg)] += immw
        cpu._set_flags(cpu.registers[Register(reg)])

    @Operation(arg_def='rr')
    def add_r(cpu: 'CPU', dst: int, src: int):
        """
        add.r dst, src - ADD Register

        dst += src
        """
        cpu.registers[Register(dst)] += cpu.registers[Register(src)]
        cpu._set_flags(cpu.registers[Register(dst)])

    @Operation(arg_def='rb')
    def sub_b(cpu: 'CPU', reg: int, immb: int):
        """
        sub.b dst, IMM_BYTE - SUBtract Byte, immediate

        dst -= IMM_BYTE
        """
        cpu.registers[Register(reg)] -= immb
        cpu._set_flags(cpu.registers[Register(reg)])

    @Operation(arg_def='rb')
    def sub_w(cpu: 'CPU', reg: int, immw: int):
        """
        sub.b dst, IMM_WORD - SUBtract Word, immediate

        dst -= IMM_WORD
        """
        cpu.registers[Register(reg)] -= immw
        cpu._set_flags(cpu.registers[Register(reg)])

    @Operation(arg_def='rr')
    def sub_r(cpu: 'CPU', dst: int, src: int):
        """
        sub.r dst, src - SUBtract Register

        dst -= src
        """
        cpu.registers[Register(dst)] -= cpu.registers[Register(src)]
        cpu._set_flags(cpu.registers[Register(dst)])

    @Operation(arg_def='rw')
    def cmp_w(cpu: 'CPU', reg: int, immw: int):
        """
        cmp.w reg, IMM_WORD - CoMPare register with Word, set flags
        """
        cpu._set_flags(cpu.registers[Register(reg)] - immw)

    @Operation(arg_def='rr')
    def cmp_r(cpu: 'CPU', reg_a: int, reg_b: int):
        """
        cmp.r reg_a, reg_b - CoMPare two registers, set flags
        """
        cpu._set_flags(cpu.registers[Register(reg_a)] - cpu.registers[Register(reg_b)])

    @Operation(arg_def='a')
    def je_rel(cpu: 'CPU', addr: int):
        if cpu.registers.F & Flag.Zero:
            cpu.registers.IP += addr

    @Operation(arg_def='a')
    def ja_rel(cpu: 'CPU', addr: int):
        if cpu.registers.F & Flag.Greater:
            cpu.registers.IP += addr

    @Operation(arg_def='a')
    def jae_rel(cpu: 'CPU', addr: int):
        if cpu.registers.F & (Flag.Equal | Flag.Greater):
            cpu.registers.IP += addr

    @Operation(arg_def='a')
    def jb_rel(cpu: 'CPU', addr: int):
        if not (cpu.registers.F & (Flag.Equal | Flag.Greater)):
            cpu.registers.IP += addr

    @Operation(arg_def='a')
    def jbe_rel(cpu: 'CPU', addr: int):
        if not (cpu.registers.F & Flag.Greater):
            cpu.registers.IP += addr

    @Operation(arg_def='a')
    def loop_rel(cpu: 'CPU', addr: int):
        """
        loop.rel IMM_ADDR_REL

        if C > 0:
            C -= 1
            IP += IMM_ADDR_REL
        """
        if cpu.registers.C > 0:
            cpu.registers.C -= 1
            cpu.registers.IP += addr

    @Operation()
    def halt(cpu: 'CPU'):
        """ halt - stops the machine """
        raise HaltRequested()

    @Operation()
    def dbg(cpu: 'CPU'):
        """ dbg - prints current state of the VM """
        print(cpu)


class InvalidOpcodeFault(Fault):
    pass


class CPU:
    OPERATIONS_BY_OPCODE = {o.opcode: o for o in Operations.__dict__.values() if isinstance(o, Operation)}
    OPERATIONS_BY_MNEMONIC = {o.mnemonic: o for o in Operations.__dict__.values() if isinstance(o, Operation)}

    def __init__(self):
        self.registers = RegisterSet()

        self.program = None
        self.ram = None
        self.call_stack = None

    def _set_flags(self, value: int):
        self.registers.F = (Flag.Zero & (value == 0)
                            | Flag.Greater & (value > 0))

    def _log_instruction(self,
                         op: Operation,
                         args: List[int],
                         op_memory: List[int]):
        args_str = ', '.join(str(x) for x in args)

        byte_fmt_len = len('%x' % 2**(self.program.char_bit - 1))
        byte_fmt = '%0{0}x'.format(byte_fmt_len)
        bytecode_str = ' '.join(byte_fmt % b for b in op_memory)

        logging.debug('%08x  %-8s %-20s %s' % (self.registers.IP, op.mnemonic, args_str, bytecode_str))

    def execute(self,
                program: Memory,
                ram: Memory,
                stack: Memory):
        self.registers.IP = 0
        self.registers.SP = len(ram)
        self.registers.RP = len(stack)

        self.program = program
        self.ram = ram
        self.call_stack = stack

        self.gpu = GPU(width=80, height=24)

        try:
            while True:
                try:
                    idx = self.registers.IP

                    try:
                        op = self.OPERATIONS_BY_OPCODE[program[idx]]
                    except KeyError as err:
                        raise InvalidOpcodeFault('invalid opcode: %d (%x) at address %08x'
                                                 % (program[idx], program[idx], idx)) from err

                    args = op.decode_args(memory=program, addr=idx + op.opcode_size_bytes)
                    self._log_instruction(op, args, program[idx:idx+op.size_bytes])

                    self.registers.IP = idx + op.size_bytes
                    op.run(self, *args)
                except Fault as err:
                    # TODO: add fault handlers?
                    logging.error(err)

                self.gpu.refresh()
        except HaltRequested:
            pass
        except KeyboardInterrupt:
            print(self)

        self.gpu.refresh(force=True)

    def __str__(self):
        return ('--- REGISTERS ---\n'
                '%s\n'
                '--- PROGRAM ---\n'
                '%s\n'
                '--- RAM ---\n'
                '%s\n'
                '--- CALL_STACK ---\n'
                '%s\n' % (self.registers, self.program, self.ram,
                          self.call_stack.make_dump(DataType.from_fmt('a').alignment)))
