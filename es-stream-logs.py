#!/usr/bin/env python

"""

Streams logs from elasticsearch, hopefully providing a quicker way to
query than Kibana, at least for ad-hoc queries.

"""

from datetime import datetime
import os
import sys
import time

from elasticsearch import Elasticsearch
import elasticsearch

from flask import Flask, Response, abort, escape, request

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

    return f"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Stream logs!</title>
</head>

<body>
    <h1>Stream logs!</h1>

    <pre><em>Streams logs from elasticsearch, controllable via query parameters.

Loads (much) faster than Kibana, queries can be generated easily.</em>


GET /     - documentation

GET /logs - stream logs from elasticsearch

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

    - <strong>q</strong>: elastic search query string query
        (See <a href="https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax">https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax</a>)

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

    - <strong>fmt</strong>: "html" or "json"
      defaults to "html", "json" outputs one log entry per line as a json object
  </pre>

  <h3>Examples:</h3>

  <ul>
    <li><a href="/logs?level=ERROR">/logs?level=ERROR</a></li>
    <li><a href="/logs?application_name=api&level=ERROR,WARN">/logs?application_name=api&level=ERROR,WARN</a></li>
    <li><a href="/logs?level=INFO&q=password">/logs?level=INFO&q=password</a></li>
    <li><a href="/logs?level=INFO&q=password&fmt=json&fields=@timestamp,hostname,message,stack_trace">/logs?level=INFO&q=password&fmt=json&fields=@timestamp,hostname,message,stack_trace</a></li>
  <ul>
</body>
    """

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

def aggregation(es, query: Query):
    """ Do aggregation query. """

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
    resp = es.search(index=query.index, body=es_query)

    total_count = 0
    max_count = 0
    num_results_buckets = resp['aggregations']['num_results']['buckets']
    for bucket in num_results_buckets:
        total_count += bucket['doc_count']
        max_count = max(max_count, bucket['doc_count'])

    query_str = ", ".join([f"{item[0]}={item[1]}" for item in query.args.items()])
    img = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" class="chart" width="100%" height="125"
     xmlns:xlink="http://www.w3.org/1999/xlink">
    <title id="title">Aggregation for query: """ + query_str + """</title>
    <style>
    svg {
        font-family: monospace;
    }

    rect {
        fill: #00b2a5;
        fill-opacity: 0.5;
        stroke-width: 1px;
        stroke: #00b2a5;
    }

    g text {
        text-anchor: middle;
        white-space: pre;

        display: none;
    }

    g:hover text {
        display: block;
    }
    </style>
    """

    #num_hits = resp['hits']['total']['value']
    avg_count = 0

    if num_results_buckets:
        avg_count = int(total_count / len(num_results_buckets))

    img += f"""<text x="10" y="14">count per {interval}: max: {max_count}, avg: {avg_count}</text>"""

    bucket_width = scale.factor * interval_s * 1000

    for bucket in num_results_buckets:
        count = bucket['doc_count']
        key = bucket['key_as_string']
        height = int((count / max_count) * 100)
        pos_x = scale.map(bucket['key'])
        bucket_logs_url = logs_url + f"&from={bucket['key']}&to={bucket['key']+interval_s*1000}"
        img += f"""<g>
    <a target="_parent" xlink:href="{escape(bucket_logs_url)}">
    <rect width="{bucket_width}%" height="{height}%" y="{100-height}%" x="{pos_x}%"></rect>
    </a>
    <text y="75%" x="{pos_x}%">{key}
(count: {count})</text>
</g>
"""

    img += "</svg>"

    #return Response(json.dumps(resp), content_type="application/json")
    return Response(img, content_type="image/svg+xml")

@APP.route('/aggregation.svg')
def serve_aggregation():
    """ Serve aggregation view. """

    es_client, resp = es_client_from(request)
    if resp:
        return resp

    query = from_request_args(CONFIG, request.args)
    return aggregation(es_client, query)

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
    while True:
        try:
            query_count += 1
            es_query = query.to_elasticsearch(last_timestamp)
            resp = es.search(index=query.index, body=es_query)
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
            yield renderer.no_results(es_query)
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

            if query.fields:
                source = filter_dict(source, query.fields)

            timestamp = int(parse_doc_timestamp(hit['_source']['@timestamp']).timestamp()*1000)
            if isinstance(last_timestamp, str):
                last_timestamp = timestamp
            else:
                last_timestamp = max(timestamp, last_timestamp)

            yield renderer.result(hit, source)
        seen = last_seen

        if query.to_timestamp != 'now' and all_hits_seen:
            yield renderer.end()
            return

        # print space to try and keep connection open
        yield " "

        time.sleep(1)

def es_client_from(req):
    """ Create elastic search client from request. """

    if ES_USER is None or ES_USER is None:
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
