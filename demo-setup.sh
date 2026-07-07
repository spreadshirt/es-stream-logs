#!/bin/sh

curl localhost:9200/logs-default-pipeline/_doc -H 'Content-Type: application/json' -d'{"@timestamp":"'$(date --utc '+%Y-%m-%dT%H:%M:%SZ')'", "application_name": "test", "hostname": "'$(hostname)'", "level": "INFO", "message": "hi!", "tracing": {"trace_id": "'$RANDOM'"}}'
