import datetime
import time
import unittest

from es_stream_logs import parse_doc_timestamp, parse_timestamp


class ParseTimestampTestCase(unittest.TestCase):
    def test_full(self):
        self.assertEqual(0, parse_timestamp("1970-01-01T00:00:00Z"))
        self.assertEqual(1635774591, parse_timestamp("2021-11-01T13:49:51Z"))

    def test_date(self):
        self.assertEqual(1635724800, parse_timestamp("2021-11-01"))
        self.assertEqual(1910131200, parse_timestamp("2030-07-13"))

    def test_relative_minutes(self):
        now = time.time()
        times = ["now", "now-1m", "now-10m", "now-30m", "now-90m"]
        offsets = [0, 60, 60 * 10, 60 * 30, 60 * 90]
        for i, t in enumerate(times):
            with self.subTest(t):
                self.assertTrue(abs((now - offsets[i]) - parse_timestamp(t)) < 0.1)

    def test_relative_hours(self):
        now = time.time()
        times = ["now", "now-1h", "now-3h", "now-10h", "now-48h"]
        offsets = [0, 1 * 60 * 60, 3 * 60 * 60, 10 * 60 * 60, 48 * 60 * 60]
        for i, t in enumerate(times):
            with self.subTest(t):
                self.assertTrue(abs((now - offsets[i]) - parse_timestamp(t)) < 0.1)

    def test_relative_days(self):
        now = time.time()
        times = ["now", "now-1d", "now-3d", "now-14d", "now-40d"]
        offsets = [0,
                   1 * 24 * 60 * 60,
                   3 * 24 * 60 * 60,
                   14 * 24 * 60 * 60,
                   40 * 24 * 60 * 60]
        for i, t in enumerate(times):
            with self.subTest(t):
                self.assertTrue(abs((now - offsets[i]) - parse_timestamp(t)) < 0.1)

    def test_epoch_millis(self):
        self.assertEqual(0, parse_timestamp("0"))
        self.assertEqual(1635774591, parse_timestamp("1635774591000"))


class ParseDocTimestampTestCase(unittest.TestCase):
    def test_full(self):
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0),
                         parse_doc_timestamp('1970-01-01T00:00:00Z'))
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0),
                         parse_doc_timestamp('1970-01-01T00:00:00.000Z'))
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0, 0, 123000),
                         parse_doc_timestamp('1970-01-01T00:00:00.123Z'))
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0, 0, 123456),
                         parse_doc_timestamp('1970-01-01T00:00:00.123456Z'))

    def test_too_long(self):
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0, 0, 123456),
                         parse_doc_timestamp('1970-01-01T00:00:00.123456999Z'))
        self.assertEqual(datetime.datetime(1970, 1, 1, 0, 0, 0, 123456),
                         parse_doc_timestamp('1970-01-01T00:00:00.1234569999999999999999Z'))

    def test_invalid(self):
        self.assertRaises(ValueError, lambda: parse_doc_timestamp("not a timestamp"))

        self.assertRaises(ValueError, lambda: parse_doc_timestamp('1970-01-01T00:00:00+01:00'))
