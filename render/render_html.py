""" Handles HTML rendering """

import json
import string

import elasticsearch
from flask import escape

from config import Config
from query import Query

class HTMLRenderer:
    """ Renders query result as HTML. """

    def __init__(self, config: Config, query: Query):
        self.config = config
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
"""

        start += self.render_query()

        start += """
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

    def render_query(self):
        """ Render query params and things. """

        res = """<form id="query" method="GET" action="/logs" autocomplete="off">"""

        res += """<select name="dc" title="datacenter">"""
        for datacenter in self.config.endpoints.keys():
            selected = ""
            if datacenter == self.query.datacenter:
                selected = " selected"
            res += f"""
    <option value="{datacenter}"{selected}>{datacenter}</option>"""
        res += """</select>"""

        res += f"""<input type="text" name="index" title="elasticsearch index" list="indices"
    value="{self.query.index}" autocomplete="on" />"""
        res += """<datalist id="indices">"""
        for index in self.config.indices:
            res += f"""<option value="{index}">{index}</option>"""
        res += """</datalist>"""

        res += f"""<input type="search" name="q" value="{self.query.query_string or ""}"
    placeholder="query string query" />"""

        for field, value in self.query.args.items():
            classes = "field-filter"
            if field.startswith("-"):
                classes += " exclude"
            res += f"""<span class="{classes}">
    <label for="{field}">{field}:</label>
    <input type="text" name="{field}" value="{value}" />
</span>"""

        res += f"""<span class="time">
    <input type="text" name="from" value="{self.query.from_timestamp}" />
    <input type="text" name="to" value="{self.query.to_timestamp}" />
</span>
"""

        res += """<input type="submit" value="Update" />"""

        res += """</form>"""
        return res

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
            if field in self.config.field_format and val:
                fmt = self.config.field_format[field]
                val = FieldFormatter().format(fmt, __query=self.query.as_params(),
                                              dc=self.query.datacenter, **hit['_source'])

            result += f"    <td data-field=\"{escape(field)}\" class=\"{' '.join(classes)}\">"
            result += "<div class=\"field-container\">"
            result += f"{val}"
            result += "</div>"
            result += "<span class=\"filter filter-include\" title=\"Filter for results matching value\">🔎</span>"
            result += "<span class=\"filter filter-exclude\" title=\"Exclude results matching value\">🗑</span>"
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

class FieldFormatter(string.Formatter):
    """ Custom formatter test gets nested dot-separated fields from an object. """

    def get_value(self, key, args, kwargs):
        val = kwargs.get(key)
        if isinstance(val, dict):
            return DotMap(val)
        return val

class DotMap(dict):
    """ A tiny map that allows key access via ".key" syntax. """

    def __getattr__(self, attr):
        return self.get(attr)
