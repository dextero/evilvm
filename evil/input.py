import os
import sys
import tty
import termios
import select
from typing import Optional

class Input:
    def __init__(self):
        self._saved_attrs = None

    def __enter__(self):
        self._saved_attrs = termios.tcgetattr(sys.stdin)
        # reopen the stream in binary mode and disable buffering
        # prevents weird buffering of escape sequences
        sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)
        tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, _type, _value, _traceback):
        self._saved_attrs = termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved_attrs)

    def get_char(self) -> Optional[int]:
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            return sys.stdin.read(1)[0]
