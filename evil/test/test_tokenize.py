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

    def test_preserves_whitespace_in_quotes(self):
        self.assertEqual(['"foo \t\nbar"'], tokenize('"foo \t\nbar"'))
        self.assertEqual(['"foo bar"', 'baz'], tokenize('"foo bar" baz'))
        self.assertEqual(['"foo bar"', '"baz qux"'], tokenize('"foo bar" "baz qux"'))

        self.assertEqual(["'foo \t\nbar'"], tokenize("'foo \t\nbar'"))
        self.assertEqual(["'foo bar'", "baz"], tokenize("'foo bar' baz"))
        self.assertEqual(["'foo bar'", "'baz qux'"], tokenize("'foo bar' 'baz qux'"))

    def test_escapes_quotes_with_backslash(self):
        self.assertEqual([r'"foo bar\" \"baz qux"'], tokenize(r'"foo bar\" \"baz qux"'))
        self.assertEqual([r"'foo bar\' \'baz qux'"], tokenize(r"'foo bar\' \'baz qux'"))

    def test_allows_unclosed_quotes(self):
        self.assertEqual(['"foo bar'], tokenize('"foo bar'))
        self.assertEqual(["'foo bar"], tokenize("'foo bar"))

    def test_separates_punctuation(self):
        self.assertEqual(['foo', ',', 'bar'], tokenize('foo, bar'))
        self.assertEqual(['(', 'foo', 'bar', ')'], tokenize('(foo bar)'))
        self.assertEqual(['foo', '-', '>', '*', 'bar'], tokenize('foo->*bar'))

    def test_number(self):
        self.assertEqual(['42'], tokenize('42'))

    def test_bitshift(self):
        self.assertEqual(['<<'], tokenize('<<'))
        self.assertEqual(['>>'], tokenize('>>'))
        self.assertEqual(['<<', '<'], tokenize('<<<'))
        self.assertEqual(['>>', '>>', '>'], tokenize('>>>>>'))
