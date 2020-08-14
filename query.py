""" This module handles query parsing and translation to elasticsearch. """

import fastapi
import starlette.datastructures
import urllib.parse

from config import Config

ONLY_ONCE_ARGUMENTS = ["from", "to", "dc", "index", "interval"]


def from_request(config, request: fastapi.Request):
    """ Create query from request args. """
    return Query(config, **flatten_params(request.query_params))


def flatten_params(query_params: starlette.datastructures.QueryParams):
    params = {}
    for key in query_params.keys():
        if key in ["fmt"]:
            continue
        params[key] = ",".join(query_params.getlist(key))
    return params


class Query:
    """ A Query contains all information necessary for handling a query
    to elasticsearch. """

    def __init__(self, config: Config, **kwargs):
        self.datacenter = kwargs.pop("dc", config.default_endpoint)
        self.index = kwargs.pop("index", "application-*")

        self.from_timestamp = kwargs.pop("from", "now-15m")
        self.to_timestamp = kwargs.pop("to", "now")

        self.interval = kwargs.pop("interval", "auto")

        self.aggregation_terms = kwargs.pop("aggregation_terms", None)
        self.aggregation_size = int(kwargs.pop("aggregation_size", 5))
        self.percentiles_terms = kwargs.pop("percentiles_terms", None)
        self.percentiles = list(map(float, kwargs.pop("percentiles", "50,90,99").split(",")))
        self.percentiles_str = ",".join(map(lambda p: str(int(p) if p.is_integer() else p), self.percentiles))

        self.max_results = kwargs.pop("max_results", 500)
        if self.max_results != "all":
            self.max_results = int(self.max_results)

        self.timeout = int(kwargs.pop("timeout", 30))

        self.sort = kwargs.pop("sort", "asc")

        self.query_string = kwargs.pop("q", None)

        fields = kwargs.pop("fields", None)
        self.fields_original = fields
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
            if key.startswith("-"):  # exclude results of this filter
                exclude = True
                key = key[1:]

            if key.startswith(":"):  # deactivate/ignore this filter (ui feature)
                continue

            special = True
            if key.startswith("\\"):  # don't parse special characters in filter
                special = False
                key = key[1:]

            match_kind = "match_phrase"
            if key.startswith("~"):
                match_kind = "match"
                key = key[1:]
            elif key.startswith("/"):
                match_kind = "regexp"
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
                if special and "," in val:
                    filters.append({"bool": {
                        "should": [{match_kind: {key: v}} for v in val.split(',')]
                    }})
                else:
                    filters.append({match_kind: {key: val}})

            if exclude:
                excluded_filters.extend(filters)
            else:
                required_filters.extend(filters)

        timerange = {"range": {"@timestamp": {"gte": from_timestamp, "lt": self.to_timestamp}}}
        if self.sort == "desc" and self.from_timestamp != from_timestamp:
            timerange = {"range": {"@timestamp": {"gte": self.from_timestamp, "lt": from_timestamp}}}
        query = {
            "size": num_results,
            "sort": [{"@timestamp": {"order": self.sort}}],
            "track_total_hits": True,
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
        inner_aggs = {}
        if self.aggregation_terms:
            inner_aggs[self.aggregation_terms] = {
                "terms": {
                    "field": self.aggregation_terms,
                    "size": self.aggregation_size,
                }
            }

        if self.percentiles_terms:
            inner_aggs[self.percentiles_terms] = {
                "percentiles": {
                    "field": self.percentiles_terms,
                    "percents": self.percentiles,
                }
            }

        aggregation = {
            name: {
                "date_histogram": {
                    "field": "@timestamp",
                    "interval": interval,
                    "time_zone": "UTC",
                    "min_doc_count": 1,
                },
                "aggs": inner_aggs,
            }
        }
        if self.percentiles_terms:
            aggregation[self.percentiles_terms] = inner_aggs[self.percentiles_terms]
        return aggregation

    def as_url(self, base_url):
        """ Render query as url. """
        return base_url + '?' + self.as_params()

    def as_params(self, with_param=None, without_param=None):
        """ Render query as query params. """
        params = [('dc', self.datacenter),
                  ('index', self.index),
                  ('from', self.from_timestamp),
                  ('to', self.to_timestamp),
                  ('interval', self.interval),
                  ]
        args = list(self.args.items())
        if with_param:
            args += [with_param]
        if without_param and not without_param[0] in ["aggregation_terms", "percentiles_terms"]:
            args.remove(without_param)
        params += args
        if self.aggregation_terms and not ("aggregation_terms", self.aggregation_terms) == without_param:
            params += [('aggregation_terms', self.aggregation_terms),
                       ('aggregation_size', str(self.aggregation_size))]
        if self.percentiles_terms and not ("percentiles_terms", self.percentiles_terms) == without_param:
            params += [('percentiles_terms', self.percentiles_terms),
                       ('percentiles', ",".join(map(str, self.percentiles)))]
        if self.interval != "auto":
            params += [('interval', self.interval)]
        if self.query_string:
            params += [("q", self.query_string)]
        if self.fields_original:
            params += [("fields", self.fields_original)]
        return urllib.parse.urlencode(params)


def collect_fields(cfg, fields, **kwargs):
    """ Collects fields by the given ones, or one of the default ones
        from the configuration. """
    additional_fields = None
    if isinstance(fields, str) and fields.startswith(","):
        additional_fields = [remove_prefix(field, ",") for field in fields.split(',')[1:]]

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
