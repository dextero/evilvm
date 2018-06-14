import sys
import time
import logging

from evil.utils import group
from evil.fault import Fault

class GPUFault(Fault):
    """ GPU access error """
    pass

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
        if n >= sys.maxunicode:
            raise GPUFault('invalid character value: %d' % n)

        self._pixels[self._curr_y * self._width + self._curr_x] = n
        self._curr_x += 1
        self._normalize_curr_pos()

    def seek(self, x: int, y: int):
        if (x < 0 or x >= self._width
                or y < 0 or y >= self._height):
            raise GPUFault('%d, %d seek position is invalid for screen of size %d x %d'
                           % (x, y, self._width, self._height))
        self._curr_x = x
        self._curr_y = y

    def _refresh_now(self):
        screen_str = ''
        for line in group(self._pixels, self._width):
            line_str = ''.join(chr(n) if chr(n).isprintable() else ' ' for n in line)
            screen_str += line_str + '\n'

        sys.stdout.write(screen_str)
        sys.stdout.write('\n')
        sys.stdout.flush()

    def refresh(self, force=False):
        now = time.time()
        if force or (now - self._refresh_last_time >= self._refresh_interval_s):
            logging.debug('refresh interval: %f', now - self._refresh_last_time)
            self._refresh_last_time = now
            self._refresh_now()
