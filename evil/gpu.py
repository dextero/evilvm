import sys
import time

from evil.utils import group


class GPU:
    def __init__(self,
                 width: int,
                 height: int,
                 refresh_rate_hz: int = 60):
        self._width = width
        self._height = height

        self._refresh_rate_hz = refresh_rate_hz
        self._refresh_last_time = time.time()

        self._pixels = [0] * (width * height)

        self._curr_x = 0
        self._curr_y = 0

    @property
    def _refresh_interval_s(self) -> float:
        return 1.0 / self._refresh_rate_hz

    def _normalize_curr_pos(self):
        quotient, self._curr_x = divmod(self._curr_x, self._width)
        self._curr_y = (self._curr_y + quotient) % self._height

    def put(self, n: int):
        assert n < sys.maxunicode
        self._pixels[self._curr_y * self._width + self._curr_x] = n
        self._curr_x += 1
        self._normalize_curr_pos()

    def _refresh_now(self):
        screen_str = ''
        for line in group(self._pixels, self._width):
            line_str = ''.join(' ' if chr(n).isspace() else chr(n) for n in line)
            screen_str += line_str + '\n'

        sys.stdout.write(screen_str)
        sys.stdout.write('\n')
        sys.stdout.flush()

    def refresh(self, force=False):
        now = time.time()
        if force or (now - self._refresh_last_time >= self._refresh_interval_s):
            self._refresh_last_time = now
            self._refresh_now()
