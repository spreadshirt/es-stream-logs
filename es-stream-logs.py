#!/usr/bin/env python

"""

Streams logs from elasticsearch, hopefully providing a quicker way to
query than Kibana, at least for ad-hoc queries.

"""

from datetime import datetime
import json
import os
import random
import sys
import time
from urllib.parse import urlparse, parse_qsl

from elasticsearch import Elasticsearch
import elasticsearch

from flask import Flask, Response, abort, request

from jinja2 import Template

# project internal modules
import config
from query import Query, from_request_args
import render
import tinygraph

APP = Flask(__name__)

ES_USER = os.environ.get('ES_USER', None)
ES_PASSWORD = os.environ.get('ES_PASSWORD', None)

@APP.route('/favicon.ico')
def favicon_route():
    """ Favicon (search glass). """
    return APP.send_static_file('search.ico')

@APP.route('/')
def index_route():
    """ GET / """

    index = Template(r"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Stream logs!</title>

    <style>
    h1, h2, h3 {
        margin: 0;
    }

    pre {
        white-space: pre-wrap;
    }

    a .medium {
        opacity: 0.6;
    }

    a .low {
        opacity: 0.25;
    }
    </style>
</head>

<body>
    <h1>Stream logs!</h1>

    <pre><em>Streams logs from elasticsearch, controllable via query parameters.

Loads (much) faster than Kibana, queries can be generated easily.</em>
    <ul>{% for query in queries -%}
        <li><a href="{{ query | e }}">{{ highlight_query(query) }}</a></li>
    {%- endfor %}</ul>
GET /       - documentation

GET /raw    - get raw search response from elasticsearch (parameters same as for /logs)
GET /query  - get query that would be sent to elasticsearch (parameters same as for /logs)

GET /aggregation.svg - get rendered histogram (parameters same as for /logs)

GET /logs   - stream logs from elasticsearch

  Query parameters:

    - <strong>dc</strong>: "dc1", "dc3" or "dc2"
      defaults to "dc1"
    - <strong>index</strong>: index to query
      defaults to "application-*"

    Result selection:

    - use `field=value` or `field=value1,value2`
      as query parameters to <strong>require</strong> a field to match certain values

      e.g.:

      - `application_name=api`
      - `application_name=api,login,registration&level=ERROR`
      - `level=ERROR`

    - use `-field=value` to <strong>exclude</strong> specific values

    - use `field=&gt;value` to require a fields' values are <strong>greater than</strong> value
    - use `field=&lt;value` to require a fields' values are <strong>less than</strong> value

    - use `field` (without `=value`) to require that a field <strong>exists</strong>
    - use `-field` to require that a field <strong>does not exist</strong>

    - <strong>q</strong>: <a href="https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax">elastic search query string query</a>

    Aggregations:

    - <strong>aggregation_terms</strong>: count number of messages per term, e.g. `aggregation_terms=level` to aggregate per log level.
      each term gets a unique color.  some special colors are used for http status codes and log levels.
    - <strong>aggregation_size</strong>: how many terms to aggregate, default is `5`.

    - <strong>percentiles_terms</strong>: collect percentiles for a field, e.g. `percentiles_terms=duration`.
      for html and svg output this is visualized as lines on each histogram bar.
    - <strong>percentiles</strong>: Percentiles to collect, default is `50,90,99`.

    Timerange:

    - <strong>from</strong>: how far to fetch messages from the past, e.g. 'now-3d'
      defaults to 'now-5m'
    - <strong>to</strong>: last timestamp to fetch messages for
      defaults to 'now'

    Output:

    - <strong>fields</strong>: select fields for output

        If no fields are specified, default fields will be selected from
        configuration, allowing application-specific default fields.

        To add fields to the default ones, use `fields=,additional-field`.

    - <strong>timeout</strong>: elasticsearch timeout in seconds, default is `10` seconds.
    - <strong>max_results</strong>: maximum results to load in html view, default is `5000`.

    - <strong>fmt</strong>: "html" or "json"
      defaults to "html", "json" outputs one log entry per line as a json object</pre>

</body>
</html>""")

    return index.render(queries=CONFIG.queries, highlight_query=highlight_query)

def highlight_query(query_url):
    u = urlparse(query_url)
    query = parse_qsl(u.query)

    param_tmpl = Template("""<span class="{{ highlight_param(qp) | e }}">{{ qp | e }}={{ qv | e }}</span>""")
    return u.path + "?" + "&".join([param_tmpl.render(highlight_param=highlight_param, qp=qp, qv=qv) for qp, qv in query])

def highlight_param(query_param):
    if query_param in ["index", "dc", "from", "to"]:
        return "medium"
    elif query_param in ["aggregation_terms", "aggregation_size", "percentiles_terms", "percentiles", "interval"]:
        return "low"
    else:
        return ""

def nested_get(dct, keys):
    """ Gets keys recursively from dict, e.g. nested_get({test: inner: 42}, ["test", "inner"])
        would return the nested `42`. """
    for key in keys:
        if isinstance(dct, list):
            dct = dct[int(key)]
        else:
            dct = dct[key]
    return dct

def filter_dict(source, fields):
    """ Filters source to only contain keys from fields. """
    res = {}
    for key in fields:
        try:
            if key in source:
                val = source[key]
            else:
                val = nested_get(source, key.split("."))
            res[key] = val
        except (IndexError, KeyError, ValueError):
            pass
    return res

def parse_offset(offset):
    """ Parse elastic-search style offset into seconds, e.g. 10s, 1m, 3h, 2d... """
    suffix = offset[-1]
    num = int(offset[:-1])
    offset_in_s = 0
    if suffix == "s":
        offset_in_s = num
    elif suffix == "m":
        offset_in_s = num * 60
    elif suffix == "h":
        offset_in_s = num * 60 * 60
    elif suffix == "d":
        offset_in_s = num * 24 * 60 * 60
    else:
        raise ValueError(f"could not parse offset '{offset}'")
    return offset_in_s

def parse_timestamp(timestamp):
    """ Parse elasticsearch-style timestamp, e.g. now-3h, 2019-09-09T00:00:00Z or epoch_millis. """
    now = time.time()
    if timestamp == "now":
        return now
    if timestamp.startswith("now-"):
        offset = parse_offset(timestamp[len("now-"):])
        return now - offset

    # epoch millis
    try:
        return int(timestamp) / 1000
    except ValueError:
        pass

    try:
        return time.mktime(time.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ'))
    except ValueError:
        pass

    raise ValueError(f"could not parse timestamp '{timestamp}'")

def aggregation_svg(es, query: Query):
    """ Execute aggregation query and render as an SVG. """

    is_internal = "/logs" in request.headers.get('Referer', '')
    width = query.args.pop('width', '100%' if is_internal else '1800')
    width_scale = None
    if width != '100%':
        width_scale = tinygraph.Scale(100, (0, 100), (0, int(width)))
    height = int(query.args.pop('height', '125' if is_internal else '600'))

    logs_url = query.as_url('/logs')

    from_time = parse_timestamp(query.from_timestamp)
    to_time = parse_timestamp(query.to_timestamp)
    scale = tinygraph.Scale(100, (from_time * 1000, to_time * 1000), (0, 100))
    interval = query.interval
    if interval == "auto":
        try:
            interval_s = max(1, tinygraph.time_increment(from_time, to_time, 100))
            interval = tinygraph.pretty_duration(interval_s)
        except ValueError as ex:
            raise ValueError("Could not guess interval: ", ex)
    else:
        interval_s = parse_offset(interval)

    es_query = query.to_elasticsearch(query.from_timestamp)
    es_query["aggs"] = query.aggregation("num_results", interval)
    resp = es.search(index=query.index, body=es_query, request_timeout=query.timeout)

    total_count = 0
    max_count = 0
    num_results_buckets = resp['aggregations']['num_results']['buckets']
    for bucket in num_results_buckets:
        total_count += bucket['doc_count']
        max_count = max(max_count, bucket['doc_count'])

    query_params = [('dc', query.datacenter), ('index', query.index)]
    query_params += query.args.items()
    query_params += [('from', query.from_timestamp), ('to', query.to_timestamp)]
    query_str = ", ".join([f"{item[0]}={item[1]}" for item in query_params])

    #num_hits = resp['hits']['total']['value']
    avg_count = 0

    if num_results_buckets:
        avg_count = int(total_count / len(num_results_buckets))

    bucket_width = scale.factor * interval_s * 1000

    buckets = []

    max_percentile = 0
    percentile_lines = None
    if query.percentiles_terms:
        percentile_lines = {}
        for bucket in num_results_buckets:
            percentiles = bucket[query.percentiles_terms]['values']
            for percentile in percentiles.keys():
                percentile_lines[percentile] = ""
            max_percentile = max(max_percentile, percentiles[str(query.percentiles[-1])])

    color_mapper = ColorMapper()
    for idx, bucket in enumerate(num_results_buckets):
        count = bucket['doc_count']
        from_ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(bucket['key'] / 1000))
        to_ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime((bucket['key']+interval_s*1000) / 1000))
        label_align = "middle"
        if idx / len(num_results_buckets) < 0.25:
            label_align = "start"
        elif idx / len(num_results_buckets) > (1-0.25):
            label_align = "end"
        bucket_data = {
            "count": count,
            "key": bucket['key_as_string'],
            "label": f"(count: {count})",
            "label_y": "15%" if is_internal else "50%",
            "label_align": label_align,
            "height": int((count / max_count) * 100),
            "pos_x": scale.map(bucket['key']),
            "from_ts": from_ts,
            "to_ts": to_ts,
            "logs_url": logs_url + f"&from={from_ts}&to={to_ts}",
            "aggregation_terms": query.aggregation_terms,
        }
        if query.aggregation_terms:
            offset_y = 100
            sub_buckets = bucket[query.aggregation_terms]['buckets']
            sub_buckets.sort(key=lambda bucket: bucket['key'])
            bucket_data['sub_buckets'] = []
            for sub_bucket in sub_buckets:
                sub_count = sub_bucket['doc_count']
                sub_height = max(0.25, int((sub_count / max_count) * 100))
                offset_y -= sub_height
                bucket_data['sub_buckets'].append({
                    'count': sub_count,
                    'height': sub_height,
                    'offset_y': offset_y,
                    'color': color_mapper.to_color(sub_bucket['key']),
                })
            bucket_data['label'] = "\n".join([f"{sub_bucket['key']}: {sub_bucket['doc_count']} ({(sub_bucket['doc_count'] / count) * 100 :.2f}%)" for sub_bucket in sub_buckets])

        if query.percentiles_terms:
            percentiles = bucket[query.percentiles_terms]['values']
            bucket_data['label'] += "\n\n"+" ".join([f"p{int(float(val)) if float(val).is_integer() else val}: {key:.2f}" for val, key in percentiles.items()])

            bucket_data['percentiles'] = []
            scale_percentile = tinygraph.Scale(1000, (0, max_percentile), (0, 95))
            for percentile, value in percentiles.items():
                pos_y = 100 - scale_percentile.map(value)
                if width_scale:
                    percentile_lines[percentile] += f" {width_scale.map(bucket_data['pos_x']+bucket_width/2)},{pos_y/100 * height}"

                percentile = float(percentile)
                pretty_percentile = int(percentile) if percentile.is_integer() else percentile
                bucket_data['percentiles'].append({
                        'pos_y': pos_y,
                        'name': pretty_percentile,
                        'value': value,
                        })

        buckets.append(bucket_data)

    query_title = ""
    if not is_internal:
        query_title += query_str + "\n"

    query_title += f"count per {interval}: max: {max_count}, avg: {avg_count}"

    if query.percentiles_terms:
        percentiles = resp["aggregations"]["percentiles"]["values"]
        query_title += " ("
        ps = []
        for p, val in percentiles.items():
            val = int(val) if val.is_integer() else '{:.2f}'.format(val)
            ps.append(f"p{int(float(p)) if float(p).is_integer() else p}: {val}")
        query_title += ", ".join(ps)
        query_title += ")"

    template = Template(r"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" class="chart" width="{{ width }}" height="{{ height }}" xmlns:xlink="http://www.w3.org/1999/xlink">

<title id="title">Aggregation for query: {{ query_str | e }}</title>
<style>
svg {
    font-family: monospace;
}

rect {
    fill-opacity: 0.5;
    stroke-width: 1px;
}

text {
    white-space: pre;
}

g text {
    display: none;
}

g:hover text {
    display: block;
}
</style>

<text x="10" y="14">{{ query_title | e }}</text>

{% for bucket in buckets %}
{% if bucket.aggregation_terms %}
<g class="bucket">
    <a target="_parent" alt="Logs from {{ bucket.from_ts }} to {{ bucket.to_ts }}" xlink:href="{{ bucket.logs_url | e }}">
{% for sub_bucket in bucket.sub_buckets %}
    <rect fill="{{ sub_bucket.color }}" stroke="{{ sub_bucket.color }}" width="{{ bucket_width }}%" height="{{ sub_bucket.height }}%" y="{{ sub_bucket.offset_y }}%" x="{{ bucket.pos_x }}%"></rect>
{% endfor %}
    </a>
    <text y="{{ bucket.label_y }}" x="{{ bucket.pos_x }}%" text-anchor="{{ bucket.label_align }}">{{ bucket.key | e }}
{{ bucket.label | e }}</text>
{% for percentile in bucket.percentiles %}
    <line stroke="black" x1="{{ bucket.pos_x }}%" x2="{{ bucket.pos_x + bucket_width }}%"
        y1="{{ percentile.pos_y }}%" y2="{{ percentile.pos_y }}%" />
{% endfor %}
</g>
{% else %}
<g class="bucket">
    <a target="_parent" alt="Logs from {{ bucket.from_ts }} to {{ bucket.to_ts }}" xlink:href="{{ bucket.logs_url | e }}">
    <rect fill="#00b2a5" stroke="#00b2a5" width="{{ bucket_width }}%" height="{{ bucket.height }}%" y="{{ 100-bucket.height }}%" x="{{ bucket.pos_x }}%"></rect>
    </a>
    <text y="{{ bucket.label_y }}" x="{{ bucket.pos_x }}%" text-anchor="{{ bucket.label_align }}">{{ bucket.key | e }}
{{ bucket.label | e }}</text>
{% for percentile in bucket.percentiles %}
    <line stroke="black" x1="{{ bucket.pos_x }}%" x2="{{ bucket.pos_x + bucket_width }}%"
        y1="{{ percentile.pos_y }}%" y2="{{ percentile.pos_y }}%" />
{% endfor %}
</g>
{% endif %}
{% endfor %}

{% if percentile_lines %}
    <polyline id="percentile" fill="none" stroke="rgba(100, 100, 100, 0.7)" points="{{ percentile_lines[list(percentile_lines.keys())[-1]] }}" />
{% endif %}

</svg>
""")
    return Response(template.render(list=list, width=width, height=height, query_title=query_title, bucket_width=bucket_width, buckets=buckets, percentile_lines=percentile_lines), content_type="image/svg+xml")


class ColorMapper():
    """ Maps values to colors, consistently. """

    def __init__(self):
        self.map = {}
        self.static_map = {
            "2xx": "green",
            "3xx": "lightgreen",
            "4xx": "yellow",
            "5xx": "red",
            "info": "green",
            "warn": "yellow",
            "warning": "yellow",
            "error": "red",
        }

    def to_color(self, value):
        """ Maps the given value to a color. """

        if isinstance(value, int):
            # special case for guessed http statuses
            if 200 <= value < 300:
                value = "2xx"
            elif 300 <= value < 400:
                value = "3xx"
            elif 400 <= value < 500:
                value = "4xx"
            elif 500 <= value < 600:
                value = "5xx"

        if not isinstance(value, str):
            value = str(value)

        if value.lower() in self.static_map:
            return self.static_map[value.lower()]

        if value not in self.map:
            rnd = random.Random(value)
            random_color = f"hsl({rnd.randint(0, 360)}, 90%, 50%)"
            self.map[value] = random_color

        return self.map[value]


@APP.route('/aggregation.svg')
def serve_aggregation():
    """ Serve aggregation view. """

    es_client, resp = es_client_from(request)
    if resp:
        return resp

    query = from_request_args(CONFIG, request.args)
    return aggregation_svg(es_client, query)

@APP.route('/raw')
def serve_raw():
    """ Serve raw query result from elasticsearch. """

    es_client, resp = es_client_from(request)
    if resp:
        return resp

    query = from_request_args(CONFIG, request.args)
    es_query = to_raw_es_query(query)

    resp = es_client.search(index=query.index, body=es_query, request_timeout=query.timeout)

    return Response(json.dumps(resp, indent=2), content_type="application/json")

@APP.route('/query')
def serve_query():
    """ Return the query that would be sent to elasticsearch. """

    query = from_request_args(CONFIG, request.args)
    es_query = to_raw_es_query(query)

    return Response(json.dumps(es_query, indent=2), content_type="application/json")

def to_raw_es_query(query):
    es_query = query.to_elasticsearch(query.from_timestamp, query.max_results)
    if query.aggregation_terms or query.percentiles_terms:
        from_time = parse_timestamp(query.from_timestamp)
        to_time = parse_timestamp(query.to_timestamp)
        interval = query.interval
        if interval == "auto":
            try:
                interval_s = max(1, tinygraph.time_increment(from_time, to_time, 100))
                interval = tinygraph.pretty_duration(interval_s)
            except ValueError as ex:
                raise ValueError("Could not guess interval: ", ex)
        else:
            interval_s = parse_offset(interval)

        es_query["aggs"] = query.aggregation("num_results", interval)

    return es_query

def parse_doc_timestamp(timestamp: str):
    """ Parse the timestamp of an elasticsearch document. """
    try:
        parsed = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        parsed = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
    return parsed

def remove_prefix(text, prefix):
    """ Remove prefix from text if present. """
    if text.startswith(prefix):
        return text[len(prefix):]
    return text

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

def stream_logs(es, renderer, query: Query):
    """ Contruct query and stream logs given the elasticsearch client and parameters. """

    last_timestamp = query.from_timestamp
    seen = {}

    yield renderer.start()

    query_count = 0
    results_count = 0
    results_total = 0
    while True:
        try:
            query_count += 1
            es_query = query.to_elasticsearch(last_timestamp)
            resp = es.search(index=query.index, body=es_query, request_timeout=query.timeout)
            if query_count == 1:
                results_total = resp['hits']['total']['value']
                took_ms = resp['took']
                yield renderer.num_results(results_total, took_ms)
        except elasticsearch.ConnectionTimeout as ex:
            print(ex)
            yield renderer.error(ex, es_query)
            time.sleep(1)
            continue
        except elasticsearch.ElasticsearchException as ex:
            print(ex)
            yield renderer.error(ex, es_query)
            return

        if query_count <= 1 and not resp['hits']['hits']:
            yield renderer.warning("Warning: No results matching query (Check details for query)",
                                   es_query)
            time.sleep(1)
            continue

        all_hits_seen = True
        last_seen = {}
        i = 0
        for hit in resp['hits']['hits']:

            i += 1
            source = hit['_source']
            _id = hit['_id']
            last_seen[_id] = True
            if _id in seen:
                continue

            all_hits_seen = False
            yield "\n"

            results_count += 1
            if query.max_results != "all" and results_count > query.max_results:
                msg = f"""Warning: More than {query.max_results} results (of {results_total} total),
use &max_results=N or &max_results=all to see more results."""
                yield renderer.warning(msg, es_query)
                yield renderer.end()
                return

            timestamp = int(parse_doc_timestamp(hit['_source']['@timestamp']).timestamp()*1000)
            if isinstance(last_timestamp, str):
                last_timestamp = timestamp
            else:
                if query.sort == "asc":
                    last_timestamp = max(timestamp, last_timestamp)
                else: # desc
                    last_timestamp = min(timestamp, last_timestamp)

            if query.fields:
                source = filter_dict(source, query.fields)
            yield renderer.result(hit, source)

        seen = last_seen

        if (query.sort == "desc" or query.to_timestamp != 'now') and all_hits_seen:
            yield renderer.end()
            return

        # print space to try and keep connection open
        yield " "

        time.sleep(1)

def es_client_from(req):
    """ Create elastic search client from request. """

    if ES_USER is None or ES_PASSWORD is None:
        if not req.authorization:
            resp = Response('Could not verify your access level for that URL.\n'
                            'You have to login with proper credentials',
                            401,
                            {'WWW-Authenticate': 'Basic realm="Login with  LDAP credentials"'})
            return None, resp

    datacenter = req.args.get('dc') or CONFIG.default_endpoint
    if datacenter not in CONFIG.endpoints:
        abort(400, f"unknown datacenter '{datacenter}'")

    es_client = Elasticsearch([CONFIG.endpoints[datacenter].url],
                              http_auth=(ES_USER or req.authorization.username,
                                         ES_PASSWORD or req.authorization.password))

    return es_client, None

@APP.route('/logs')
def serve_logs():
    """ Serve logs. """
    es_client, resp = es_client_from(request)
    if resp:
        return resp

    headers = {}

    query = from_request_args(CONFIG, request.args)

    fmt = request.args.get("fmt", "html")
    if fmt == "html":
        renderer = render.HTMLRenderer(CONFIG, query)
        content_type = "text/html"
        csp = [
            "default-src 'none'",
            "img-src 'self'",    # favicon
            "script-src 'self'",
            "style-src 'self'",
            "object-src 'self'", # histogram
            "frame-src 'self'",  # histogram in chromium
            ]
        headers['Content-Security-Policy'] = "; ".join(csp)
    elif fmt == "json":
        renderer = render.JSONRenderer()
        content_type = "application/json"
    else:
        raise Exception(f"unknown output format '{fmt}'")

    return Response(stream_logs(es_client, renderer, query), headers=headers,
                    content_type=content_type+'; charset=utf-8')

CONFIG = None

def run_app():
    """ Run application. """

    config_file = 'config.json'
    host = 'localhost'
    port = 3028
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    if len(sys.argv) > 2:
        host = sys.argv[2]
    if len(sys.argv) > 3:
        port = int(sys.argv[3])

    print(f"Loading config from '{config_file}'")
    global CONFIG
    CONFIG = config.from_file(config_file)

    APP.run(host=host, port=port, threaded=True)

if __name__ == "__main__":
    run_app()
