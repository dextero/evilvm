start:
    movw.i2r c, hello
    call.rel print
    jmp.rel start

print:
    lpb.r a, c
    je.rel print_done
    out
    add.b c, 1
    jmp.rel print
print_done:
    ret

hello:
    db "Hello, world!\0"
