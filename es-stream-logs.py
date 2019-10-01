#!/usr/bin/env python

"""

Streams logs from elasticsearch, hopefully providing a quicker way to
query than Kibana, at least for ad-hoc queries.

"""

from datetime import datetime
import json
import os
import sys
import time

from elasticsearch import Elasticsearch
import elasticsearch

from flask import Flask, Response, abort, escape, request

# project internal modules
import config
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

    return """
<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Stream logs!</title>
</head>

<body>
    <h1>Stream logs!</h1>

    <pre>
GET /     - documentation

GET /logs - stream logs from elasticsearch

  Parameters:

    - dc: "dc1", "dc3" or "dc2"
      defaults to "dc1"
    - index: index to query
      defaults to "application-*"

    - use `&lt;any-field&gt;=&lt;anyvalue&gt;` or `&lt;any-field&gt;=&lt;value1&gt;,&lt;value2&gt;,&lt;value3&gt;`
      as query paramters to require a field to have certain values

      e.g.:

      - `application_name=api`
      - `application_name=api,login,registration&level=ERROR`
      - `level=ERROR`

    - q: elastic search query string query
        (See https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax)

    - from: how far to fetch messages from the past, e.g. 'now-3d'
      defaults to 'now-5m'
    - to: last timestamp to fetch messages for
      defaults to 'now'

    - fmt: "text" or "json"
      defaults to "text", "json" outputs one log entry per line as a json object
    - fields: if fmt is "json", output only the given fields
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

def create_query(from_timestamp, to_timestamp, aggregate=False, num_results=500, interval="1h", **kwargs):
    """ Create elasticsearch query from (query) parameters. """

    required_filters = []
    excluded_filters = []
    query = kwargs.get("q", None)
    if query:
        required_filters.append({"query_string": {"query": query, "analyze_wildcard": True}})
        kwargs.pop("q", None)

    compare_ops = {"<": "lt", ">": "gt"}
    for key, val in kwargs.items():
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

    timerange = {"range": {"@timestamp": {"gte": from_timestamp, "lt": to_timestamp}}}
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
    if aggregate:
        query["aggs"] = {
            "num_results": {
                "date_histogram": {
                    "field": "@timestamp",
                    "interval": interval,
                    "time_zone": "UTC",
                    "min_doc_count": 0
                }
            }
        }
    return query

def parse_timestamp(timestamp):
    """ Parse elasticsearch-style timestamp, e.g. now-3h, 2019-09-09T00:00:00Z or epoch_millis. """
    now = time.time()
    if timestamp == "now":
        return now
    if timestamp.startswith("now-"):
        suffix = timestamp[len(timestamp)-1]
        num = int(timestamp[len("now-"):len(timestamp)-1])
        if suffix == "s":
            return now - num
        if suffix == "m":
            return now - num * 60
        if suffix == "h":
            return now - num * 60 * 60
        if suffix == "d":
            return now - num * 24 * 60 * 60

        raise ValueError(f"could not parse timestamp '{timestamp}'")

    # epoch millis
    try:
        return int(timestamp) / 1000
    except ValueError:
        pass

    try:
        return time.mktime(time.strptime('2019-09-09T00:00:03Z', '%Y-%m-%dT%H:%M:%SZ'))
    except ValueError:
        pass

    raise ValueError(f"could not parse timestamp '{timestamp}'")

def aggregation(es, index="application-*", interval="auto", **kwargs):
    """ Do aggregation query. """

    kwargs_query = map(lambda item: item[0] + "=" + item[1],
                       [('dc', kwargs.get('dc', CONFIG.default_endpoint)),
                        ('index', index)] + list(kwargs.items()))
    logs_url = '/logs?' + "&".join(kwargs_query)

    # remove unused params
    kwargs.pop('dc', None)
    kwargs.pop('fields', None)

    from_timestamp = kwargs.get("from", "now-5m")
    to_timestamp = kwargs.get("to", "now")
    # remove from and to because they are not fields, None to prevent KeyError
    kwargs.pop("from", None)
    kwargs.pop("to", None)

    if interval == "auto":
        try:
            from_time = parse_timestamp(from_timestamp)
            to_time = parse_timestamp(to_timestamp)
            scale = tinygraph.Scale(100, (from_time * 1000, to_time * 1000), (0, 100))
            interval_s = max(1, tinygraph.time_increment(from_time, to_time, 100))
            interval = tinygraph.pretty_duration(interval_s)
        except ValueError as ex:
            raise ValueError("Could not guess interval: ", ex)

    query_str = ", ".join([f"{item[0]}={item[1]}" for item in kwargs.items()])

    query = create_query(from_timestamp, to_timestamp, interval=interval,
                         num_results=0, aggregate=True, **kwargs)
    resp = es.search(index=index, body=query)

    total_count = 0
    max_count = 0
    num_results_buckets = resp['aggregations']['num_results']['buckets']
    for bucket in num_results_buckets:
        total_count += bucket['doc_count']
        max_count = max(max_count, bucket['doc_count'])

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

    args = consolidate_args(request.args, exceptions=ONLY_ONCE_ARGUMENTS)
    return aggregation(es_client, **args)

def link_trace_logs(dc, index, from_timestamp, to_timestamp, trace_id):
    """ Create link for logs about trace_id. """
    params = []
    if dc != 'dc1':
        params.append(('dc', dc))
    if index != 'application-*':
        params.append(('index', index))
    if from_timestamp != 'now-5m':
        params.append(('from', from_timestamp))
    if to_timestamp != 'now':
        params.append(('to', to_timestamp))
    params.append(('tracing.trace_id', trace_id))
    return '/logs?' + '&'.join(map(lambda item: item[0] + "=" + item[1], params))

def parse_doc_timestamp(timestamp: str):
    """ Parse the timestamp of an elasticsearch document. """
    try:
        parsed = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        parsed = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
    return parsed

def stream_logs(es, dc='dc1', index="application-*", fmt="html", fields=None, separator=" ", **kwargs):
    """ Contruct query and stream logs given the elasticsearch client and parameters. """

    if fields:
        fields = fields.split(',')
    else:
        default_fields = CONFIG.find_default_fields(index=index, **kwargs)
        if default_fields:
            fields = default_fields

    kwargs_query = map(lambda item: item[0] + "=" + item[1],
                       [('dc', dc), ('index', index)] + list(kwargs.items()))
    aggregation_url = '/aggregation.svg?' + "&".join(kwargs_query)

    from_timestamp = kwargs.get("from", "now-5m")
    to_timestamp = kwargs.get("to", "now")
    # remove from and to because they are not fields, None to prevent KeyError
    kwargs.pop("from", None)
    kwargs.pop("to", None)

    last_timestamp = from_timestamp
    seen = {}

    # send something so we return an initial response
    yield ""

    if fmt == "html":
        yield """<!doctype html>
<html>
<head>
    <link rel="stylesheet" href="/static/pretty.css" />
</head>
<body>

<section class="stats">
    <p><span id="stats-num-hits">0</span> hits</p>
</section>

<div id="histogram_container">
<object id="histogram" type="image/svg+xml" data=""" + '"' + aggregation_url + '"' + """></object>
</div>

<script src="/static/enhance.js" defer async></script>

<table>
<thead>
<tr>
"""

        yield "<td></td>" # for expand placeholder
        for field in fields:
            yield f"<td class=\"field\" data-class=\"field-{escape(field)}\">{escape(field)}</td>"

        yield """
</tr>
</thead>

<tbody>
"""

    while True:
        try:
            query = create_query(last_timestamp, to_timestamp, **kwargs)
            resp = es.search(index=index, body=query)
        except elasticsearch.ConnectionTimeout as ex:
            print(ex)
            yield " " # keep connection open
            time.sleep(1)
            continue
        except elasticsearch.AuthenticationException as ex:
            yield str(ex)
            return

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

            if fields != "all":
                source = filter_dict(source, fields)

            timestamp = int(parse_doc_timestamp(hit['_source']['@timestamp']).timestamp()*1000)
            if isinstance(last_timestamp, str):
                last_timestamp = timestamp
            else:
                last_timestamp = max(timestamp, last_timestamp)

            if fmt == "json":
                yield json.dumps(source)
            if fmt == "html":
                yield f"<tr class=\"row\" data-source=\"{escape(json.dumps(hit['_source']))}\">\n"
                yield "<td class=\"toggle-expand\">+</td>"
                for field in fields:
                    val = escape(source.get(field, ''))
                    classes = [f"field-{escape(field)}"]
                    if field == "_source":
                        val = json.dumps(hit['_source'])
                        val = f"<div class=\"source-flattened\">{escape(val)}</div>"
                    if field == "tracing.trace_id" and val:
                        classes += ["break-strings"]
                        trace_id = escape(val)
                        val = f"<a href=\"https://tracing.example.com/?traceId={trace_id}&dc={dc}\">{trace_id}</a>"
                        trace_id_logs = link_trace_logs(dc, index, 'now-14d', to_timestamp, trace_id)
                        val += f" <a class=\"trace-logs\" title=\"Logs for trace_id {trace_id}\"href=\"{trace_id_logs}\">…</a>"
                    yield f"    <td data-field=\"{escape(field)}\" class=\"{' '.join(classes)}\">"
                    yield val
                    yield "<span class=\"filter filter-include\">🔎</span>"
                    yield "<span class=\"filter filter-exclude\">🗑</span>"
                    yield "</td>\n"
                yield "</tr>\n"
                yield f"<tr class=\"source source-hidden\"><td colspan=\"{1 + len(fields)}\"></td></tr>\n"
            else:
                if fields != "all":
                    yield separator.join((str(val) for val in source.values()))
                else:
                    try:
                        hostname = source.get('hostname', source.get('HOSTNAME', '<no-hostname>'))
                        yield f"{source['@timestamp']} -- {source['level']} [{hostname}] {source['message']}"
                        if 'thread_name' in source:
                            yield f": {source['thread_name']}"
                        if 'stack_trace' in source:
                            yield f"\n{source['stack_trace']}"
                    except KeyError:
                        yield str(source)
        seen = last_seen

        if to_timestamp != 'now' and all_hits_seen:
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

def consolidate_args(args, exceptions=None):
    """ Consolidates arguments from a werkzeug.datastructures.MultiDict
        into our internal comma-separated format. """
    res = {}
    for key, values in args.to_dict(flat=False).items():
        if exceptions and key in exceptions:
            res[key] = values[-1]
        else:
            res[key] = ','.join(values)
    return res

ONLY_ONCE_ARGUMENTS = ["fmt", "from", "to", "dc", "index", "interval"]

@APP.route('/logs')
def serve_logs():
    """ Serve logs. """
    es_client, resp = es_client_from(request)
    if resp:
        return resp

    fmt = request.args.get("fmt", "html")
    content_type = "text/html"
    if fmt == "json":
        content_type = "application/json"
    elif fmt == "text":
        content_type = "text/plain"

    args = consolidate_args(request.args, exceptions=ONLY_ONCE_ARGUMENTS)
    return Response(stream_logs(es_client, **args),
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
