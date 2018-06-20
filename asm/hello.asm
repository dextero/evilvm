start:
    movw.i2r c, hello
    call print
    jmp start

print:
    lpb.r a, c
    je print_done
    out
    add.b c, 1
    jmp print
print_done:
    ret

hello:
    db "Hello, world!\0"
