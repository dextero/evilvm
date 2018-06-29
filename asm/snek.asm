WIDTH = 80
HEIGHT = 24

SNAKE_INIT_X = WIDTH / 2
SNAKE_INIT_Y = HEIGHT / 2

MAX_X = WIDTH - 1
MAX_Y = HEIGHT - 1
INNER_WIDTH = WIDTH - 2
INNER_HEIGHT = HEIGHT - 2

MAP = 0
MAP_END = WIDTH * HEIGHT

WALL = 0b1_000_000

NONE  = 0b000
RIGHT = 0b001
UP    = 0b010
LEFT  = 0b011
DOWN  = 0b100

FROM_SHIFT = 0
FROM       = 0b111 << FROM_SHIFT
FROM_NONE  = NONE  << FROM_SHIFT
FROM_RIGHT = RIGHT << FROM_SHIFT
FROM_UP    = UP    << FROM_SHIFT
FROM_LEFT  = LEFT  << FROM_SHIFT
FROM_DOWN  = DOWN  << FROM_SHIFT

TO_SHIFT = 3
TO       = 0b111 << TO_SHIFT
TO_NONE  = NONE  << TO_SHIFT
TO_RIGHT = RIGHT << TO_SHIFT
TO_UP    = UP    << TO_SHIFT
TO_LEFT  = LEFT  << TO_SHIFT
TO_DOWN  = DOWN  << TO_SHIFT

APPLE_X = MAP_END + 0
APPLE_Y = MAP_END + 1

SNAKE_HEAD_X = MAP_END + 2
SNAKE_HEAD_Y = MAP_END + 3

CURR_DIRECTION = MAP_END + 4

start:
    call reset

main_loop:
    call handle_input
    call draw_board
    call snake_update

    jmp main_loop


handle_input:
    ; -1 = EOF - nothing to read
    in
    jb handle_input_ret
    ; escape?
    cmp.b a, 27
    jne handle_input

    in
    jb handle_input_ret

    cmp.b a, '['
    jne handle_input

    in
    jb handle_input_ret

    ; 'A' = 65 = UP; 66 = DOWN; 67 = RIGHT; 68 = LEFT
    sub.b a, 'A'
    jb handle_input
    cmp.b a, 3
    ja handle_input

    add.w a, handle_input_arrows
    lpb.r b, a
    movb.r2m CURR_DIRECTION, b

handle_input_ret:
    ret

handle_input_arrows:
    db UP, DOWN, RIGHT, LEFT


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

    movb.i2r b, WALL
    movb.i2r c, WIDTH
    call memset

    movb.i2r c, HEIGHT - 2
reset_middle_next:
    push c
     movb.i2r c, 1
     call memset

     movb.i2r b, NONE
     movb.i2r c, WIDTH - 2
     call memset

     movb.i2r b, WALL
     movb.i2r c, 1
     call memset
    pop c
    loop reset_middle_next

    movb.i2r c, WIDTH
    call memset

    movw.i2r a, (SNAKE_INIT_Y * WIDTH) + SNAKE_INIT_X
    movb.i2r b, FROM_LEFT | TO_NONE
    stb.r a, b

    sub.b a, 1
    movb.i2r b, FROM_LEFT | TO_RIGHT
    stb.r a, b

    sub.b a, 1
    movb.i2r b, FROM_NONE | TO_RIGHT
    stb.r a, b

    movb.i2r a, SNAKE_INIT_X
    movb.r2m SNAKE_HEAD_X, a
    movb.i2r a, SNAKE_INIT_Y
    movb.r2m SNAKE_HEAD_Y, a

    movb.i2r a, RIGHT
    movb.r2m CURR_DIRECTION, a

    ret


draw_board_char_table:
    db " <v>^   "
    db "> \-/   "
    db "^\ /|   "
    db "<-/ \   "
    db "v/|\    "
    db "        "
    db "        "
    db "        "
    db "X"


draw_board:
    movb.i2r a, 0
    movb.i2r b, 0
    seek a, b

    movb.i2r a, MAP
    movw.i2r c, WIDTH * HEIGHT
draw_board_char:
    ldb.r b, a
    add.w b, draw_board_char_table
    push a
     lpb.r a, b
     out
    pop a
    add.b a, 1
    loop draw_board_char

    ret


invert_direction:
    sub.b a, 1
    add.w a, inverted_directions
    lpb.r a, a
    ret

inverted_directions:
    db LEFT, DOWN, RIGHT, UP


offset_from_direction:
    ; TODO: check for 1 <= a <= 4
    sub.b a, 1
    add.w a, offset_by_direction
    lpb.r a, a
    ret

offset_by_direction:
    db 1, -WIDTH, -1, WIDTH


xy_from_direction:
    ; TODO: check for 1 <= a <= 4
    sub.b a, 1
    add.w a, y_delta_by_direction
    lpb.r b, a
    add.w a, x_delta_by_direction - y_delta_by_direction
    lpb.r a, a
    ret

x_delta_by_direction:
    db 1, 0, -1, 0

y_delta_by_direction:
    db 0, -1, 0, 1


snake_update:
    ; c = snake_head_idx
    movb.m2r b, SNAKE_HEAD_X
    movb.m2r c, SNAKE_HEAD_Y

    mul.b c, WIDTH
    add.r c, b

    ; TODO: check for wall
    ; update head
    push c
     ; update old head
     ; TODO: assert TO == NONE?
     ldb.r b, c
     movb.m2r a, CURR_DIRECTION
     shl.b a, TO_SHIFT
     or.r a, b
     stb.r c, a

     ; c = new HEAD offset
     movb.m2r a, CURR_DIRECTION
     call offset_from_direction
     add.r c, a

     ldb.r a, c
     je snake_no_collision
     halt
snake_no_collision:

     ; set FROM on new head pos
     movb.m2r a, CURR_DIRECTION
     call invert_direction
     shl.b a, FROM_SHIFT
     stb.r c, a

     ; update HEAD pos
     movb.m2r a, CURR_DIRECTION
     call xy_from_direction

     movb.m2r c, SNAKE_HEAD_X
     add.r a, c
     movb.r2m SNAKE_HEAD_X, a

     movb.m2r c, SNAKE_HEAD_Y
     add.r b, c
     movb.r2m SNAKE_HEAD_Y, b
    pop c

snake_update_next:
    ; a = map[curr_idx]
    ldb.r a, c

    ; a = a.from
    and.b a, FROM
    shr.b a, FROM_SHIFT
    ; no 'from' direction, i.e. we're at the end
    ; we need to store NONE at current and clear FROM in previous
    je snake_update_end

    push c
     ; c += offset_from_direction(a)
     call offset_from_direction
     add.r c, a

     ; a = map[curr_idx]
     ldb.r a, c

     ; a = a.from
     and.b a, FROM
     shr.b a, FROM_SHIFT
     je snake_update_end
    ; discard previous offset
    pop b
    jmp snake_update_next

snake_update_end:
     ; clear current, i.e. last segment
     movb.i2r a, NONE
     stb.r c, a
    ; get previous offset, clear FROM field
    pop c
    ldb.r a, c
    and.b a, ~FROM
    stb.r c, a

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
    movw.m2r a, SNAKE_HEAD_X
    movw.m2r b, SNAKE_HEAD_Y
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
