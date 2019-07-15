#!/usr/bin/env python

from datetime import datetime
import json
import os
import sys
import time

from elasticsearch import Elasticsearch
import elasticsearch

from flask import Flask, Response, abort, request

app = Flask(__name__)

es_user = os.environ.get('ES_USER', None)
es_password = os.environ.get('ES_PASSWORD', None)

datacenters = ['dc1', 'dc3', 'dc2']

@app.route('/')
def index():
    return """
<!doctype html
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

    - use `<any-field>=<anyvalue>` or `<any-field>=<value1>,<value2>,<value3>`
      as query paramters to require a field to have certain values

      e.g.:

      - `application_name=api`
      - `application_name=api,login,registration&level=ERROR`
      - `level=ERROR`

    - q: elastic search query string query
        (See https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax)

    - offset_seconds: how far to fetch messages from the past in seconds
      defaults to 300, i.e. five minutes

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
	for key in keys:
		dct = dct[key]
	return dct

def filter_dict(source, fields):
	res = {}
	for key in fields:
		try:
			val = nested_get(source, key.split("."))
			res[key] = val
		except KeyError:
			pass
	return res

# curl 'http://kibana-dc1.example.com/elasticsearch/_msearch' -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0' -H 'Accept: application/json, text/plain, */*' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: http://kibana-dc1.example.com/app/kibana' -H 'content-type: application/x-ndjson' -H 'kbn-version: 5.6.9' -H 'DNT: 1' -H 'Connection: keep-alive' -H 'Pragma: no-cache' -H 'Cache-Control: no-cache' --data $'{"index":["application-2019.02.21"],"ignore_unavailable":true,"preference":1550757631050}\n{"version":true,"size":500,"sort":[{"@timestamp":{"order":"desc","unmapped_type":"boolean"}}],"query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}},"_source":{"excludes":[]},"aggs":{"2":{"date_histogram":{"field":"@timestamp","interval":"30s","time_zone":"UTC","min_doc_count":1}}},"stored_fields":["*"],"script_fields":{},"docvalue_fields":["@timestamp","time"],"highlight":{"pre_tags":["@kibana-highlighted-field@"],"post_tags":["@/kibana-highlighted-field@"],"fields":{"*":{"highlight_query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}}}},"fragment_size":2147483647}}\n'
@app.route('/logs')
def stream_logs():
    def now_ms():
        return int(datetime.utcnow().timestamp()*1000)

    def results(es, dc='dc1', index="application-*", q=None, offset_seconds=300, fmt="text", fields="all", separator=" ", **kwargs):
        if fields != "all":
            fields = fields.split(',')

        last_timestamp = now_ms() - int(offset_seconds)*1000
        seen = {}

        required_filters = []
        if q:
            required_filters.append({"query_string": {"query": q}})

        for key, val in kwargs.items():
            required_filters.append({ "bool" : { "should": [{"term": {key: v}} for v in val.split(',')]}})

        # send something so we return an initial response
        yield ""

        while True:
            now = now_ms()

            timerange = { "range": { "@timestamp": { "gte": last_timestamp, "lt": now, "format": "epoch_millis" } } }
            try:
                resp = es.search(index=index,
                        body={
                            "size": 100,
                            "sort": [{"@timestamp":{"order": "asc"}}],
                            "query": {
                                "bool": { "must": [*required_filters, timerange] }
                                }
                            })
            except elasticsearch.ConnectionTimeout as e:
                print(e)
                time.sleep(1)
                continue
            except elasticsearch.AuthenticationException as e:
                yield str(e)
                return

            last_seen = {}
            i = 0
            for hit in resp['hits']['hits']:
                i+=1
                source = hit['_source']
                _id = hit['_id']
                last_seen[_id] = True
                if _id in seen:
                    continue

                ts = int(datetime.strptime(source['@timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()*1000)
                last_timestamp = max(ts, last_timestamp)

                if fmt == "json":
                    if fields != "all":
                        source = filter_dict(source, fields)
                    yield json.dumps(source)
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
                yield "\n"
            seen = last_seen

            time.sleep(1)

    if es_user is None or es_password is None:
        if not request.authorization:
            return Response('Could not verify your access level for that URL.\n'
                            'You have to login with proper credentials',
                            401,
                            {'WWW-Authenticate': 'Basic realm="Login with  LDAP credentials"'})

    dc = request.args.get('dc') or 'dc1'
    if dc not in datacenters:
        abort(400, f"unknown datacenter '{dc}'")

    es = Elasticsearch([f"https://es-log-{dc}.example.com:443"],
            http_auth=(es_user or request.authorization.username, es_password or request.authorization.password))

    return Response(results(es, **request.args), content_type='text/plain')

host = 'localhost'
port = 3028
if len(sys.argv) > 1:
    host = sys.argv[1]
if len(sys.argv) > 2:
    port = int(sys.argv[2])
app.run(host=host, port=port, threaded=True)
