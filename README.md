# es-stream-logs

Streams logs from elasticsearch, controllable via query parameters.
Loads (much) faster than Kibana, queries can be generated easily.

See <http://localhost:3028> for docs and examples.

## TODO

- [ ] support for excluding specific results (~`NOT`)
- [ ] [`range` queries](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html)
- [ ] dynamic query modification ("click to exclude/include" like in kibana, "+/-" buttons)
- [ ] generate links in rundeck-bot
- [ ] ads (on devblog ;))
- [ ] show histogram for timerange on top by default (only for first query?)

## Misc

- `./static/search.ico` is [from Wikipedia](https://commons.wikimedia.org/w/skins/Vector/images/search.svg), converted with Inkscape
