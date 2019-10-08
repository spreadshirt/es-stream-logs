""" This module handles query parsing and translation to elasticsearch. """

from config import Config

ONLY_ONCE_ARGUMENTS = ["from", "to", "dc", "index", "interval"]

def from_request_args(config, args):
    """ Create query from request args. """
    args = consolidate_args(args, ONLY_ONCE_ARGUMENTS)
    return Query(config, **args)

def consolidate_args(args, exceptions=None):
    """ Consolidates arguments from a werkzeug.datastructures.MultiDict
        into our internal comma-separated format. """
    res = {}
    for key, values in args.to_dict(flat=False).items():
        if key in ["fmt"]:
            continue

        if exceptions and key in exceptions:
            res[key] = values[-1]
        else:
            res[key] = ','.join(values)
    return res

class Query:
    """ A Query contains all information necessary for handling a query
    to elasticsearch. """

    def __init__(self, config: Config, **kwargs):
        self.datacenter = kwargs.pop("dc", config.default_endpoint)
        self.index = kwargs.pop("index", "application-*")

        self.from_timestamp = kwargs.pop("from", "now-5m")
        self.to_timestamp = kwargs.pop("to", "now")
        self.interval = kwargs.pop("interval", "auto")

        self.query_string = kwargs.pop("q", None)

        fields = kwargs.pop("fields", None)
        self.fields = collect_fields(config, fields, index=self.index, **kwargs)

        self.args = kwargs

    def to_elasticsearch(self, from_timestamp, num_results=500):
        """ Create elasticsearch query from (query) parameters. """

        required_filters = []
        excluded_filters = []
        if self.query_string:
            required_filters.append(
                {"query_string": {"query": self.query_string, "analyze_wildcard": True}})

        compare_ops = {"<": "lt", ">": "gt"}
        for key, val in self.args.items():
            exclude = False
            if key.startswith("-"):
                exclude = True
                key = key[1:]

            filters = []
            if val == "":
                filters.append({"exists": {"field": key}})
            elif val[:1] in compare_ops:
                compare_op = compare_ops[val[:1]]
                try:
                    filters.append({"range": {key: {compare_op: int(val[1:])}}})
                except ValueError:
                    msg = f"value for range query on '{key}' must be a number, but was '{val[1:]}'"
                    raise ValueError(msg)
            else:
                if "," in val:
                    filters.append({"bool" : {
                        "should": [{"match": {key: v}} for v in val.split(',')]
                        }})
                else:
                    filters.append({"match": {key: val}})

            if exclude:
                excluded_filters.extend(filters)
            else:
                required_filters.extend(filters)

        timerange = {"range": {"@timestamp": {"gte": from_timestamp, "lt": self.to_timestamp}}}
        query = {
            "size": num_results,
            "sort": [{"@timestamp":{"order": "asc"}}],
            "query": {
                "bool": {
                    "must": [*required_filters, timerange],
                    "must_not": excluded_filters
                    }
                }
            }
        return query

    def aggregation(self, name, interval):
        """ Return (date_histogram) aggregation query. """
        return {
            name: {
                "date_histogram": {
                    "field": "@timestamp",
                    "interval": interval,
                    "time_zone": "UTC",
                    "min_doc_count": 0
                }
            }
        }

    def as_url(self, base_url):
        """ Render query as url. """
        params = map(lambda item: item[0] + "=" + item[1],
                     [('dc', self.datacenter),
                      ('index', self.index),
                      ('from', self.from_timestamp),
                      ('to', self.to_timestamp),
                     ] + list(self.args.items()))
        return base_url + '?' + "&".join(params)

def collect_fields(cfg, fields, **kwargs):
    """ Collects fields by the given ones, or one of the default ones
        from the configuration. """
    additional_fields = None
    if isinstance(fields, str) and fields.startswith(","):
        additional_fields = [remove_prefix(field, ",") for field in fields.split(',')]

    if fields and not additional_fields:
        fields = fields.split(',')
    else:
        default_fields = cfg.find_default_fields(**kwargs)
        if default_fields:
            fields = default_fields
            if additional_fields:
                fields += additional_fields
    return fields

def remove_prefix(text, prefix):
    """ Remove prefix from text if present. """
    if text.startswith(prefix):
        return text[len(prefix):]
    return text

if __name__ == '__main__':
    import unittest

    class QueryTest(unittest.TestCase):
        """ Test query class. """

        def setUp(self):
            self.config = Config(default_endpoint='default', endpoints=[], default_fields={})

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
            self.assertEqual(query.as_url('/'), '/?dc=default&index=application-*&from=now-5m&to=now')

            query = Query(self.config, level='WARN')
            self.assertEqual(query.as_url('/'), '/?dc=default&index=application-*&from=now-5m&to=now&level=WARN')

        def assert_defaults(self, query, args=None):
            """ Assert query params. """
            self.assertEqual(query.datacenter, 'default')
            self.assertEqual(query.index, 'application-*')
            self.assertEqual(query.from_timestamp, 'now-5m')
            self.assertEqual(query.to_timestamp, 'now')
            self.assertEqual(query.query_string, None)
            self.assertEqual(query.fields, None)
            self.assertEqual(query.args, args or {})

    unittest.main()
