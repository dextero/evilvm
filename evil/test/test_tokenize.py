import unittest

from evil.utils import tokenize

class TokenizeTest(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(['foo'], tokenize('foo'))
        self.assertEqual(['foo'], tokenize(' foo'))
        self.assertEqual(['foo'], tokenize('foo '))
        self.assertEqual(['foo'], tokenize(' foo '))
        self.assertEqual(['foo'], tokenize('\tfoo\n'))

    def test_splits_on_whitespace(self):
        self.assertEqual(['foo', 'bar'], tokenize('foo bar'))
        self.assertEqual(['foo', 'bar'], tokenize('foo   bar'))
        self.assertEqual(['foo', 'bar'], tokenize('foo \t  \nbar'))
