#!/usr/bin/env python

from datetime import datetime
import json
import os
import sys
import time

from elasticsearch import Elasticsearch
#from elasticsearch_dsl import Search

from flask import Flask, Response, request

user = os.environ['ES_USER']
password = os.environ['ES_PASSWORD']

es_dc1 = Elasticsearch(['https://elasticsearch-dc1.example.com:443'], http_auth=(user, password))
es_dc1.info()

es_dc3 = Elasticsearch(['https://elasticsearch-dc3.example.com:443'], http_auth=(user, password))
es_dc3.info()

app = Flask(__name__)

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

    - dc: "dc1" or "dc3"
    - application_name: "api", "api,login", "all"
      defaults to "api"
    - level: "ERROR", "WARN,ERROR"
      defaults to "ERROR"
    - q: elastic search query string query
        (See https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-syntax)

    - offset_seconds: how far to fetch messages from the past in seconds
      defaults to 300, i.e. five minutes

    - fmt: "text" or "json"
      defaults to "text", "json" outputs one log entry per line as a json object
    - fields: if fmt is "json", output only the given fields

  Examples:

    - /logs?application_name=all&level=ERROR
    - /logs?application_name=api&level=ERROR,WARN
    - /logs?application_name=all&level=INFO&q=password
    - /logs?application_name=all&level=INFO&q=password&fmt=json&fields=@timestamp,hostname,message,stack_trace
    </pre>
</body>
    """

# curl 'http://kibana-dc1.example.com/elasticsearch/_msearch' -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0' -H 'Accept: application/json, text/plain, */*' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: http://kibana-dc1.example.com/app/kibana' -H 'content-type: application/x-ndjson' -H 'kbn-version: 5.6.9' -H 'DNT: 1' -H 'Connection: keep-alive' -H 'Pragma: no-cache' -H 'Cache-Control: no-cache' --data $'{"index":["application-2019.02.21"],"ignore_unavailable":true,"preference":1550757631050}\n{"version":true,"size":500,"sort":[{"@timestamp":{"order":"desc","unmapped_type":"boolean"}}],"query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}},"_source":{"excludes":[]},"aggs":{"2":{"date_histogram":{"field":"@timestamp","interval":"30s","time_zone":"UTC","min_doc_count":1}}},"stored_fields":["*"],"script_fields":{},"docvalue_fields":["@timestamp","time"],"highlight":{"pre_tags":["@kibana-highlighted-field@"],"post_tags":["@/kibana-highlighted-field@"],"fields":{"*":{"highlight_query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}}}},"fragment_size":2147483647}}\n'
@app.route('/logs')
def stream_logs():
    def now_ms():
        return int(datetime.utcnow().timestamp()*1000)

    def results(es, application_name, log_levels, query, offset_seconds, fmt, json_fields):
        if json_fields != "all":
            json_fields = json_fields.split(',')

        last_timestamp = now_ms() - offset_seconds*1000
        seen = {}

        while True:
            now = now_ms()

            musts = []
            levels_query = { "bool" : { "should": [{"term": {"level": l}} for l in log_levels.split(',')]}}
            musts.append(levels_query)
            application_names_query = { "bool" : { "should": [{"term": {"application_name": app}} for app in application_name.split(',')]}}
            if application_name != "all":
                musts.append(application_names_query)
            if query:
                musts.append({"query_string": {"query": query}})
            timerange = { "range": { "@timestamp": { "gte": last_timestamp, "lt": now, "format": "epoch_millis" } } }
            musts.append(timerange)
            resp = es.search(index="application-*",
                    body={
                        "size": 10,
                        "sort": [{"@timestamp":{"order": "asc"}}],
                        "query": {
                            "bool": { "must": musts }
                        }
                    })

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
                    if json_fields != "all":
                        source = { key: source[key] for key in json_fields if key in source }
                    yield json.dumps(source)
                    yield "\n"
                else:
                    try:
                        hostname = source.get('hostname', source.get('HOSTNAME', '<no-hostname>'))
                        yield f"{source['@timestamp']} -- {source['level']} [{hostname}] {source['message']}"
                        if 'thread_name' in source:
                            yield f": {source['thread_name']}"
                        if 'stack_trace' in source:
                            yield f"\n{source['stack_trace']}"
                        yield "\n"
                    except KeyError as e:
                        print(e)
                        yield source
            seen = last_seen

            time.sleep(1)

    es = es_dc1
    if request.args.get('dc') == "dc3":
        es = es_dc3

    application_name = request.args.get('application_name') or 'api'
    log_level = request.args.get('level') or 'ERROR'
    query = request.args.get('q')
    offset_seconds = int(request.args.get('offset_seconds') or 5*60)
    fmt = request.args.get('fmt') or 'text'
    json_fields = request.args.get('fields') or 'all'
    return Response(results(es, application_name, log_level, query, offset_seconds, fmt, json_fields), content_type='text/plain')

host = 'localhost'
port = 12345
if len(sys.argv) > 1:
    host = sys.argv[1]
if len(sys.argv) > 2:
    port = int(sys.argv[2])
app.run(host=host, port=port)
