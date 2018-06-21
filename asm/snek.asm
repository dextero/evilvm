WIDTH = 80
HEIGHT = 24

MAX_X = WIDTH - 1
MAX_Y = HEIGHT - 1
INNER_WIDTH = WIDTH - 2
INNER_HEIGHT = HEIGHT - 2

MAP = 0
MAP_END = WIDTH * HEIGHT

FIELD_WALL = 1
FIELD_EMPTY = 2
FIELD_SNAKE_RIGHT = 3
FIELD_SNAKE_UP = 4
FIELD_SNAKE_LEFT = 5
FIELD_SNAKE_DOWN = 6
FIELD_SNAKE_END = 7
FIELD_FRUIT = 8
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
    call reset
    call draw_board
    ;call draw_snake
    halt


; IN:
; a - address
; b - fill
; c - size, bytes;
memset:
    cmp.b c, 0
    je memset_exit

memset_next:
    stb.r a, b
    add.b a, 1
    loop memset_next

memset_exit:
    ret


reset:
    movb.i2r a, MAP

    movb.i2r b, FIELD_WALL
    movb.i2r c, WIDTH
    call memset

    movb.i2r c, HEIGHT - 2
reset_middle_next:
    push c
     movb.i2r c, 1
     call memset

     movb.i2r b, FIELD_EMPTY
     movb.i2r c, WIDTH - 2
     call memset

     movb.i2r b, FIELD_WALL
     movb.i2r c, 1
     call memset
    pop c
    loop reset_middle_next

    movb.i2r c, WIDTH
    call memset

    ret


; A, B - x/y position of the left end
; C - length
draw_horizontal_line:
    seek a, b
    movb.i2r a, '-'
    sub.b c, 1

draw_horizontal_line_next:
    out
    loop draw_horizontal_line_next

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
    loop draw_vertical_line_next

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
    call draw_horizontal_line

    movb.i2r a, 1
    movb.i2r b, MAX_Y
    movb.i2r c, MAX_X - 1
    call draw_horizontal_line

    movb.i2r a, 0
    movb.i2r b, 1
    movb.i2r c, MAX_Y - 1
    call draw_vertical_line

    movb.i2r a, MAX_X
    movb.i2r b, 1
    movb.i2r c, MAX_Y - 1
    call draw_vertical_line

    ret


draw_board_char_table:
    db "?X -|-|.@"


draw_board:
    movb.i2r a, 0
    movb.i2r b, 0
    seek a, b

    movb.i2r c, HEIGHT
draw_board_row:
    push c
     movb.i2r c, WIDTH

draw_board_char:
     add.b a, 1
     ldb.r b, a
     add.w b, draw_board_char_table
     push a
      lpb.r a, b
      out
     pop a
     loop draw_board_char

    pop c
    loop draw_board_row

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
    ; TODO: constant
    cmp.b c, 2
    jb draw_snake_segment_fail

    cmp.b c, 5
    ja draw_snake_segment_fail

    ; TODO: constant
    sub.b c, 2
    mul.b c, sizeof a
    add.w c, draw_snake_segment_advance
    call.r c

    call xy_to_offset
    ret

draw_snake_segment_fail:
    halt


; IN: a, b - pos
; OUT: c - offset
xy_to_offset:
    movw.r2r c, b
    mul.b c, WIDTH
    add.r c, a
    ret


draw_snake:
    movb.m2r a, SNAKE_HEAD_X
    movb.m2r b, SNAKE_HEAD_Y
    seek a, b

    movb.i2r a, 'o'
    out

    call xy_to_offset
    ; TODO: should it be valid?
    ldb.r c, c

draw_snake_next:
    call get_next_snake_segment

    ; TODO: constant
    cmp.b c, 6
    jae draw_snake_end

    call draw_snake_segment
    jmp draw_snake_next

draw_snake_end:
    ret
