# es-stream-logs

Streams logs from elasticsearch, controllable via query parameters.
Loads (much) faster than Kibana, queries can be generated easily.

See <http://localhost:3028> for docs and examples.

## Configuration

See [config.json](./config.json) for examples of all of the following.

- `default_endpoint`, `endpoints`, `indices`: set up elasticsearch
    endpoints and indices to display
- `queries`: configure queries to be displayed on the start page for
    quick access
- `field_format`: customize the formatting for a given field, e.g. to
    display a field as a link to an application that provides additional
    details
- `default_fields`: configure a set of fields to use by default for a
    given query, for example fields specific to `my-app` when there is a
    filter like `app=my-app`

## Development

Use `./scripts/run` to fetch dependencies and start the server.  Then
visit <http://localhost:3028>.  Set `ES_USER` and `ES_PASSWORD` in `.env`,
otherwise basic auth credentials will be requested to connect to
elasticsearch.
