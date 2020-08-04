#!/bin/sh

curl -X PUT localhost:9200/application-$(date --utc --iso-8601=date)

curl localhost:9200/application-$(date --utc --iso-8601=date)/_doc -H 'Content-Type: application/json' -d'{"@timestamp":"'$(date --utc '+%Y-%m-%dT%H:%M:%SZ')'", "application_name": "test", "hostname": "'$(hostname)'", "level": "INFO", "message": "hi!", "tracing": {"trace_id": "'$RANDOM'"}}'
