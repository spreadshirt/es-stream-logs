# es-stream-logs

Streams logs from elasticsearch, controllable via query parameters.
Loads (much) faster than Kibana, queries can be generated easily.

See <http://localhost:3028> for docs and examples.

## Development

Use `./scripts/run` to fetch dependencies and start the server.  Then
visit <http://localhost:3028>.  Set `ES_USER` and `ES_PASSWORD`,
otherwise basic auth credentials will be requested to connect to
elasticsearch.

## TODO

- [ ] dynamic query modification ("click to exclude/include" like in kibana, "+/-" buttons)
- [ ] generate links in rundeck-bot
- [ ] ads (on devblog ;))

## Misc

- `./static/search.ico` is [from Wikipedia](https://commons.wikimedia.org/w/skins/Vector/images/search.svg), converted with Inkscape
