WIDTH = 80
HEIGHT = 24

MAX_X = WIDTH - 1
MAX_Y = HEIGHT - 1
INNER_WIDTH = WIDTH - 2
INNER_HEIGHT = HEIGHT - 2

MAP = 0
MAP_END = WIDTH * HEIGHT
; 0 - wall
; 1 - empty field
; 2 - snake, next segment right
; 3 - snake, next segment up
; 4 - snake, next segment left
; 5 - snake, next segment down
; 6 - snake, no next segment
; 7 - fruit
;
; e.g.: 
;
; XXXXXXXXX 000000000
; X       X 011111110
; X  o--. X 011222510
; X . F | X 016171510
; X '---' X 013444410
; X       X 011111110
; XXXXXXXXX 000000000

APPLE_X = MAP_END + 0
APPLE_Y = MAP_END + 1

SNAKE_HEAD_X = MAP_END + 2
SNAKE_HEAD_Y = MAP_END + 3

start:
    call.rel draw_border
    halt

; A, B - x/y position of the left end
; C - length
draw_horizontal_line:
    seek a, b
    movb.i2r a, '-'
    sub.b c, 1

draw_horizontal_line_next:
    out
    loop.rel draw_horizontal_line_next

    ret

; A, B - x/y position of the top end
; C - length
draw_vertical_line:
    seek a, b
    sub.b c, 1

draw_vertical_line_next:
    push a
     movb.i2r a, '|'
     out
    pop a
    add.b b, 1
    seek a, b
    loop.rel draw_vertical_line_next

    ret
    

draw_border:
    movb.i2r a, '/'
    movb.i2r b, 0
    movb.i2r c, 0
    seek b, c
    out

    movb.i2r b, MAX_X
    movb.i2r c, MAX_Y
    seek b, c
    out

    movb.i2r a, '\\'
    movb.i2r b, 0
    movb.i2r c, MAX_Y
    seek b, c
    out

    movb.i2r b, MAX_X
    movb.i2r c, 0
    seek b, c
    out
    
    movb.i2r a, 1
    movb.i2r b, 0
    movb.i2r c, MAX_X - 1
    call.rel draw_horizontal_line

    movb.i2r a, 1
    movb.i2r b, MAX_Y
    movb.i2r c, MAX_X - 1
    call.rel draw_horizontal_line

    movb.i2r a, 0
    movb.i2r b, 1
    movb.i2r c, MAX_Y - 1
    call.rel draw_vertical_line

    movb.i2r a, MAX_X
    movb.i2r b, 1
    movb.i2r c, MAX_Y - 1
    call.rel draw_vertical_line

    ret

; c - next direction
draw_snake_segment_advance:
    da draw_snake_segment_advance_right
    da draw_snake_segment_advance_up
    da draw_snake_segment_advance_left
    da draw_snake_segment_advance_right
    da draw_snake_segment_advance_end

; a, b - curr pos
draw_snake_segment_advance_right:
    add.b a, 1
    ret

draw_snake_segment_advance_up:
    sub.b b, 1
    ret

draw_snake_segment_advance_left:
    sub.b a, 1
    ret

draw_snake_segment_advance_down:
    add.b b, 1
    ret

draw_snake_segment_advance_end:
    ret

; a, b - curr pos
draw_snake_segment:
    seek a, b
    push a
     movb.i2r a, '.'
     out
    pop a
    ret

; IN:
; a, b - curr pos
; c - next direction
; OUT:
; a, b - new pos
; c - new next direction
get_next_snake_segment:
    cmp c, 2 ; TODO: constant
    jb.rel draw_snake_segment_fail

    cmp c, 5
    ja.rel draw_snake_segment_fail

    sub.b c, 2 ; TODO: constant
    mul.b c, sizeof(addr)
    add.w c, draw_snake_segment_advance
    call.r c

    call.rel xy_to_offset
    ret

draw_snake_segment_fail:
    halt


; IN: a, b - pos
; OUT: c - offset
xy_to_offset:
    mov.r2r c, b
    mul.b c, WIDTH
    add.r c, a
    ret


draw_snake:
    movb.m2r a, SNAKE_HEAD_X
    movb.m2r b, SNAKE_HEAD_Y
    seek a, b

    mul.b b, WIDTH
    add.r a, b
    ldb.r c, a

    movb.i2r a, 'o'
    out


draw_snake:
    movb.m2r a, SNAKE_HEAD_X
    movb.m2r b, SNAKE_HEAD_Y
    seek a, b

    movb.i2r a, 'o'
    out

    call.rel xy_to_offset
    ldb.r c, c ; TODO: should it be valid?

draw_snake_next:
    call.rel get_next_snake_segment

    cmp.b c, 6 ; TODO: constant
    jae.rel draw_snake_end

    call.rel draw_snake_segment
    jmp.rel draw_snake_next

draw_snake_end:
    ret
