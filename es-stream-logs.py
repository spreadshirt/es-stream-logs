#!/usr/bin/env python

from datetime import datetime
import os
import time

from elasticsearch import Elasticsearch
#from elasticsearch_dsl import Search

from flask import Flask, Response, request

user = os.environ['ES_USER']
password = os.environ['ES_PASSWORD']

es = Elasticsearch(['https://elasticsearch-dc1.example.com:443'], http_auth=(user, password))
es.info()

app = Flask(__name__)

# curl 'http://kibana-dc1.example.com/elasticsearch/_msearch' -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0' -H 'Accept: application/json, text/plain, */*' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: http://kibana-dc1.example.com/app/kibana' -H 'content-type: application/x-ndjson' -H 'kbn-version: 5.6.9' -H 'DNT: 1' -H 'Connection: keep-alive' -H 'Pragma: no-cache' -H 'Cache-Control: no-cache' --data $'{"index":["application-2019.02.21"],"ignore_unavailable":true,"preference":1550757631050}\n{"version":true,"size":500,"sort":[{"@timestamp":{"order":"desc","unmapped_type":"boolean"}}],"query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}},"_source":{"excludes":[]},"aggs":{"2":{"date_histogram":{"field":"@timestamp","interval":"30s","time_zone":"UTC","min_doc_count":1}}},"stored_fields":["*"],"script_fields":{},"docvalue_fields":["@timestamp","time"],"highlight":{"pre_tags":["@kibana-highlighted-field@"],"post_tags":["@/kibana-highlighted-field@"],"fields":{"*":{"highlight_query":{"bool":{"must":[{"match_all":{}},{"match_phrase":{"level":{"query":"ERROR"}}},{"match_phrase":{"application_name":{"query":"api"}}},{"range":{"@timestamp":{"gte":1550757641281,"lte":1550758541281,"format":"epoch_millis"}}}],"must_not":[]}}}},"fragment_size":2147483647}}\n'
@app.route('/')
def stream_logs():
    def now_ms():
        return int(datetime.utcnow().timestamp()*1000)

    def results(application_name, log_levels, query):
        last_timestamp = now_ms() - 5*60*1000
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

                try:
                    yield f"{source['@timestamp']} -- [{source.get('hostname', '<no-hostname>')}] {source['message']}"
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

    application_name = request.args.get('application_name') or 'api'
    log_level = request.args.get('level') or 'ERROR'
    query = request.args.get('q')
    return Response(results(application_name, log_level, query), content_type='text/plain')

app.run(host='localhost', port=12345)
