""" Handles HTML rendering """

import json

import elasticsearch
from flask import escape

from query import Query

class HTMLRenderer:
    """ Renders query result as HTML. """

    def __init__(self, query: Query):
        self.query = query

    def start(self):
        """ Render content at the "start", e.g. html head, table head, ... """

        aggregation_url = self.query.as_url('/aggregation.svg')
        start = """<!doctype html>
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

<table class="results">
<thead>
<tr>
"""
        start += "  <td></td>\n" # for expand placeholder
        for field in self.query.fields:
            field = escape(field)
            start += f"  <td class=\"field\" data-class=\"field-{field}\">{field}</td>\n"

        start += """
</tr>
</thead>

<tbody>
"""
        return start

    def result(self, hit, source):
        """ Renders a single result. """

        result = f"<tr class=\"row\" data-source=\"{escape(json.dumps(hit['_source']))}\">\n"
        result += "<td class=\"toggle-expand\">+</td>"
        for field in self.query.fields:
            val = escape(source.get(field, ''))
            classes = [f"field-{escape(field)}"]
            if field == "_source":
                source = json.dumps(hit['_source'])
                val = f"<div class=\"source-flattened\">{escape(source)}</div>"
            if field == "tracing.trace_id" and val:
                classes += ["break-strings"]
                trace_id = escape(val)
                val = f"<a href=\"https://tracing.example.com/?traceId={trace_id}&dc={self.query.datacenter}\">{trace_id}</a>"
                trace_id_logs = link_trace_logs(self.query, trace_id)
                val += f" <a class=\"trace-logs\" title=\"Logs for trace_id {trace_id}\"href=\"{trace_id_logs}\">…</a>"

            result += f"    <td data-field=\"{escape(field)}\" class=\"{' '.join(classes)}\">"
            result += "<div class=\"field-container\">"
            result += f"{val}"
            result += "</div>"
            result += "<span class=\"filter filter-include\">🔎</span>"
            result += "<span class=\"filter filter-exclude\">🗑</span>"
            result += "</td>\n"
        result += "</tr>\n"
        result += f"<tr class=\"source source-hidden\"><td colspan=\"{1 + len(self.query.fields)}\"></td></tr>\n"
        return result

    def end(self):
        """ Renders end of results. """
        return """</tbody>
</table>
</body>
</html>"""

    def no_results(self, es_query):
        """ Render no results. """

        msg = "Warning: No results matching query (Check details for query)"
        return self.__notice("warning", es_query, msg)

    def error(self, ex, es_query):
        """ Render error. """

        if isinstance(ex, elasticsearch.ConnectionTimeout):
            msg = f"Warning: Connection timeout: {ex} (Check details for query)"
            return self.__notice("warning", es_query, msg)

        msg = "ERROR!: " + str(ex)
        return self.__notice("error", es_query, msg)

    def __notice(self, class_, es_query, msg):
        width = len(self.query.fields)
        row = f"<tr data-source=\"{escape(json.dumps(es_query))}\">\n"
        row += "<td class=\"toggle-expand\">+</td> "
        row += f"<td class=\"{class_}\" colspan=\"{width}\">{escape(msg)}</td>"
        row += "</tr>\n"

        row += f"<tr class=\"source source-hidden\"><td colspan=\"{1 + width}\"></td></tr>\n"
        return row

def link_trace_logs(query: Query, trace_id: str):
    """ Create link for logs about trace_id. """
    params = []
    if query.datacenter != 'dc1':
        params.append(('dc', query.datacenter))
    if query.index != 'application-*':
        params.append(('index', query.index))
    params.append(('from', 'now-14d'))
    if query.to_timestamp != 'now':
        params.append(('to', query.to_timestamp))
    params.append(('tracing.trace_id', trace_id))
    return '/logs?' + '&'.join(map(lambda item: item[0] + "=" + item[1], params))
