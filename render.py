""" This module handles rendering of query results. """

import json

import elasticsearch
from flask import escape

class HTMLRenderer:
    """ Renders query result as HTML. """

    def start(self, datacenter, index, fields, query_args):
        """ Render content at the "start", e.g. html head, table head, ... """

        aggregation_url = query_as_url('/aggregation.svg', datacenter, index, query_args)
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

<table>
<thead>
<tr>
"""
        start += "  <td></td>\n" # for expand placeholder
        for field in fields:
            field = escape(field)
            start += f"  <td class=\"field\" data-class=\"field-{field}\">{field}</td>\n"

        start += """
</tr>
</thead>

<tbody>
"""
        return start

    def result(self, dc, index, fields, hit, source, to_timestamp):
        """ Renders a single result. """

        result = f"<tr class=\"row\" data-source=\"{escape(json.dumps(hit['_source']))}\">\n"
        result += "<td class=\"toggle-expand\">+</td>"
        for field in fields:
            val = escape(source.get(field, ''))
            classes = [f"field-{escape(field)}"]
            if field == "_source":
                source = json.dumps(hit['_source'])
                val = f"<div class=\"source-flattened\">{escape(source)}</div>"
            if field == "tracing.trace_id" and val:
                classes += ["break-strings"]
                trace_id = escape(val)
                val = f"<a href=\"https://tracing.example.com/?traceId={trace_id}&dc={dc}\">{trace_id}</a>"
                trace_id_logs = link_trace_logs(dc, index, 'now-14d', to_timestamp, trace_id)
                val += f" <a class=\"trace-logs\" title=\"Logs for trace_id {trace_id}\"href=\"{trace_id_logs}\">…</a>"

            result += f"    <td data-field=\"{escape(field)}\" class=\"{' '.join(classes)}\">"
            result += "<div class=\"field-container\">"
            result += f"{val}"
            result += "</div>"
            result += "<span class=\"filter filter-include\">🔎</span>"
            result += "<span class=\"filter filter-exclude\">🗑</span>"
            result += "</td>\n"
        result += "</tr>\n"
        result += f"<tr class=\"source source-hidden\"><td colspan=\"{1 + len(fields)}\"></td></tr>\n"
        return result

    def end(self):
        """ Renders end of results. """
        return """</tbody>
</table>
</body>
</html>"""

    def no_results(self, query, fields):
        """ Render no results. """

        msg = "Warning: No results matching query (Check details for query)"
        return self.__notice("warning", len(fields), json.dumps(query), msg)

    def error(self, query, fields, ex):
        """ Render error. """

        if isinstance(ex, elasticsearch.ConnectionTimeout):
            msg = f"Warning: Connection timeout: {ex} (Check details for query)"
            return self.__notice("warning", len(fields), json.dumps(query), msg)

        msg = "ERROR!: " + str(ex)
        return self.__notice("error", len(fields), json.dumps(query), msg)

    def __notice(self, class_, width, content, msg):
        row = f"<tr data-source=\"{escape(content)}\">\n"
        row += "<td class=\"toggle-expand\">+</td> "
        row += f"<td class=\"{class_}\" colspan=\"{width}\">{escape(msg)}</td>"
        row += "</tr>\n"

        row += f"<tr class=\"source source-hidden\"><td colspan=\"{1 + width}\"></td></tr>\n"
        return row

def query_as_url(url, datacenter, index, query_args):
    """ Render query as url. """
    kwargs_query = map(lambda item: item[0] + "=" + item[1],
                       [('dc', datacenter), ('index', index)] + list(query_args.items()))
    return url + '?' + "&".join(kwargs_query)

def link_trace_logs(dc, index, from_timestamp, to_timestamp, trace_id):
    """ Create link for logs about trace_id. """
    params = []
    if dc != 'dc1':
        params.append(('dc', dc))
    if index != 'application-*':
        params.append(('index', index))
    if from_timestamp != 'now-5m':
        params.append(('from', from_timestamp))
    if to_timestamp != 'now':
        params.append(('to', to_timestamp))
    params.append(('tracing.trace_id', trace_id))
    return '/logs?' + '&'.join(map(lambda item: item[0] + "=" + item[1], params))
