import unittest

from config import Config
from query import Query


class QueryTest(unittest.TestCase):
    """ Test query class. """

    def setUp(self):
        self.config = Config(default_endpoint='default', endpoints=[],
                             field_format={}, default_fields={})

    def test_parse_defaults(self):
        """ Test defaults. """

        query = Query(self.config)
        self.assert_defaults(query)

    def test_parse_simple(self):
        """ Test simple query. """

        query = Query(self.config, application_name="my-app", level='WARN')
        self.assert_defaults(query,
                             args={'application_name': 'my-app',
                                   'level': 'WARN'}
                             )

    def test_as_url(self):
        """ Test url conversion. """

        query = Query(self.config)
        self.assertEqual(query.as_url('/'), '/?dc=default&index=application-*&from=now-5m&to=now&interval=auto')

        query = Query(self.config, level='WARN')
        self.assertEqual(query.as_url('/'), '/?dc=default&index=application-*&from=now-5m&to=now&interval=auto&level=WARN')

    def assert_defaults(self, query, args=None):
        """ Assert query params. """
        self.assertEqual(query.datacenter, 'default')
        self.assertEqual(query.index, 'application-*')
        self.assertEqual(query.from_timestamp, 'now-5m')
        self.assertEqual(query.to_timestamp, 'now')
        self.assertEqual(query.query_string, None)
        self.assertEqual(query.fields, None)
        self.assertEqual(query.args, args or {})
