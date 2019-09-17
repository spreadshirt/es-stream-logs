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

from flask import Flask, Response, abort, request

APP = Flask(__name__)

ES_USER = os.environ.get('ES_USER', None)
ES_PASSWORD = os.environ.get('ES_PASSWORD', None)

DATACENTERS = ['dc1', 'dc3', 'dc2']

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
        dct = dct[key]
    return dct

def filter_dict(source, fields):
    """ Filters source to only contain keys from fields. """
    res = {}
    for key in fields:
        try:
            val = nested_get(source, key.split("."))
            res[key] = val
        except KeyError:
            pass
    return res

# curl 'http://kibana-dc1.example.com/elasticsearch/_msearch' -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0' -H 'Accept: application/json, text/plain, */*' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: http://kibana-dc1.example.com/app/kibana' -H 'content-type: application/x-ndjson' -H 'kbn-version: 5.6.9' -H 'DNT: 1' -H 'Connection: keep-alive' -H 'Pragma: no-cache' -H 'Cache-Control: no-cache' --data $'{"index":["application-2019.02.21"],"ignore_unavailable":true,"preference":1550757631050}\n{"version":true,"size":500,"sort":[{"@timestamp":{"order":"desc","unmapped_type":"boolean"}}],"query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}},"_source":{"excludes":[]},"aggs":{"2":{"date_histogram":{"field":"@timestamp","interval":"30s","time_zone":"UTC","min_doc_count":1}}},"stored_fields":["*"],"script_fields":{},"docvalue_fields":["@timestamp","time"],"highlight":{"pre_tags":["@kibana-highlighted-field@"],"post_tags":["@/kibana-highlighted-field@"],"fields":{"*":{"highlight_query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}}}},"fragment_size":2147483647}}\n'
@APP.route('/logs')
def stream_logs():
    def now_ms():
        return int(datetime.utcnow().timestamp()*1000)

    def results(es, dc='dc1', index="application-*", q=None, fmt="text", fields="all", separator=" ", **kwargs):
        if fields != "all":
            fields = fields.split(',')

        from_timestamp = kwargs.get("from", "now-5m")
        to_timestamp = kwargs.get("to", "now")
        # remove from and to because they are not fields, None to prevent KeyError
        kwargs.pop("from", None)
        kwargs.pop("to", None)

        last_timestamp = from_timestamp
        seen = {}

        required_filters = []
        if q:
            required_filters.append({"query_string": {"query": q, "analyze_wildcard": True}})

        for key, val in kwargs.items():
            if val == "":
                if key.startswith("-"):
                    required_filters.append({"bool": {"must_not": {"exists": {"field": key[1:]}}}})
                else:
                    required_filters.append({"exists": {"field": key}})
            else:
                required_filters.append({"bool" : {"should": [{"term": {key: v}} for v in val.split(',')]}})

        # send something so we return an initial response
        yield ""

        if fmt == "html":
            yield """<!doctype html>
<html>
<head>
    <style>
        table {
            width: 100%;
        }

        thead tr {
            font-weight: bold;
        }

        td {
            margin-right: 1em;
            border-bottom: 1px solid #ddd;
            font-size: 14px;
            font-family: monospace;
            max-width: 30em;
            word-wrap: break-word;
            overflow-y: auto;
            vertical-align: top;
        }
    </style>
</head>
<body>
<table>
<thead>
<tr>
"""

            if fields == "all":
                fields = ["@timestamp", "hostname", "level", "message", "thread_name", "stack_trace"]

            for field in fields:
                yield f"<td>{field}</td>"

            yield """
</tr>
</thead>

<tbody>
"""

        while True:
            now = now_ms()

            timerange = {"range": {"@timestamp": {"gte": last_timestamp, "lt": to_timestamp}}}
            try:
                resp = es.search(index=index,
                        body={
                            "size": 500,
                            "sort": [{"@timestamp":{"order": "asc"}}],
                            "query": {
                                "bool": {"must": [*required_filters, timerange]}
                                }
                            })
            except elasticsearch.ConnectionTimeout as ex:
                print(ex)
                time.sleep(1)
                continue
            except elasticsearch.AuthenticationException as ex:
                yield str(ex)
                return

            last_seen = {}
            i = 0
            for hit in resp['hits']['hits']:
                i += 1
                source = hit['_source']
                _id = hit['_id']
                last_seen[_id] = True
                if _id in seen:
                    continue

                yield "\n"

                ts = int(datetime.strptime(source['@timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()*1000)
                if isinstance(last_timestamp, str):
                    last_timestamp = ts
                else:
                    last_timestamp = max(ts, last_timestamp)

                if fmt == "json":
                    if fields != "all":
                        source = filter_dict(source, fields)
                    yield json.dumps(source)
                if fmt == "html":
                    try:
                        trace_id = nested_get(source, ["tracing", "trace_id"])
                        trace_id_link = f"<a href=\"https://tracing.example.com/?traceId={trace_id}&dc={dc}\">{trace_id}</a>"
                        source["tracing"]["trace_id"] = trace_id_link
                    except KeyError:
                        pass

                    source = filter_dict(source, fields)
                    yield "<tr>\n"
                    for field in fields:
                        yield f"    <td>{source.get(field, '')}</td>\n"
                    yield "</tr>\n"
                else:
                    if fields != "all":
                        source = filter_dict(source, fields)
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

            # print space to try and keep connection open
            yield " "

            time.sleep(1)

    if ES_USER is None or ES_USER is None:
        if not request.authorization:
            return Response('Could not verify your access level for that URL.\n'
                            'You have to login with proper credentials',
                            401,
                            {'WWW-Authenticate': 'Basic realm="Login with  LDAP credentials"'})

    dc = request.args.get('dc') or 'dc1'
    if dc not in DATACENTERS:
        abort(400, f"unknown datacenter '{dc}'")

    es = Elasticsearch([f"https://es-log-{dc}.example.com:443"],
                       http_auth=(ES_USER or request.authorization.username,
                                  ES_PASSWORD or request.authorization.password))

    fmt = request.args.get("fmt", "text")
    content_type = "text/plain"
    if fmt == "json":
        content_type = "application/json"
    elif fmt == "html":
        content_type = "text/html"

    return Response(results(es, **request.args), content_type=content_type+'; charset=utf-8')

if __name__ == "__main__":
    host = 'localhost'
    port = 3028
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    APP.run(host=host, port=port, threaded=True)
