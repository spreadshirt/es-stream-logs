""" Handles HTML rendering """

import copy
import json
import string

import elasticsearch

from jinja2 import Template
from markupsafe import escape

from color_mapper import ColorMapper
from config import Config
from query import Query


class HTMLRenderer:
    """ Renders query result as HTML. """

    def __init__(self, config: Config, query: Query):
        self.config = config
        self.query = query
        self.color_mapper = ColorMapper()

    def start(self):
        """ Render content at the "start", e.g. html head, table head, ... """

        aggregation_url = self.query.as_url('/aggregation.svg')
        template = Template(r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ "".join(query.as_params()) | e }} - es-stream-logs</title>
    <link rel="stylesheet" href="/static/pretty.css" />
</head>
<body>

{% block query_form %}
    <form id="query" method="GET" action="/logs" autocomplete="off">
        <select name="dc" title="datacenter">
    {% for datacenter, selected in datacenters.items() %}
            <option value="{{ datacenter | e }}" {% if selected %}selected{% endif %}>{{ datacenter | e }}</option>
    {% endfor %}
        </select>

        <input type="text" name="index" title="elasticsearch index" list="indices" size="{{ len(query.index) }}" value="{{ query.index | e }}" autocomplete="on" />
        <datalist id="indices">
    {% for index in indices %}
            <option value="{{ index | e }}">{{ index | e }}</option>
    {% endfor %}
        </datalist>

    {% if query.fields_original %}
        <input type="text" name="fields" hidden value="{{ query.fields_original | e }}" />
    {% endif %}

        <span>
            <label for="q">q:</label>
            <input type="search" name="q" value="{{ (query.query_string or "") | e}}" placeholder="query string query" />
        </span>

    {% for field, value in query.args.items() %}
        <span class="field-filter{% if field.startswith('-') %} excluded{% endif %}{% if field.startswith(':') %} disabled{% endif %}">
            <label for="{{ field | e }}">{{ field | e }}:</label>
            <input type="text" name="{{ field | e }}" size="{{ min(len(value), 30) }}" value="{{ value | e }}" />
            <span class="field-actions">
                {% if field.startswith(':') %}
                    <a title="Re-enable filter for '{{ field | e }}'" href="?{{ query.as_params(without_param=(field, value), with_param=(field[1:],value)) }}">👁</a>
                {% else %}
                    <a title="Disable filter for '{{ field | e }}'" href="?{{ query.as_params(without_param=(field, value), with_param=(':'+field,value)) }}">👁</a>
                {% endif %}
                {% if field.startswith('-') %}
                    <a title="Include '{{ field[1:] | e }}'" href="?{{ query.as_params(without_param=(field, value), with_param=(field[1:],value)) }}">¬</a>
                {% else %}
                    <a title="Exclude '{{ field | e }}'" href="?{{ query.as_params(without_param=(field, value), with_param=('-'+field,value)) }}">¬</a>
                {% endif %}
                    <a class="remove-filter" title="Remove filter for '{{ field | e }}'" href="?{{ query.as_params(without_param=(field, value)) }}">🗑</a>
            </span>
        </span>
    {% endfor %}

    {% if query.aggregation_terms %}
        <span class="field-filter">
            <label for="aggregation_terms">aggregation:</label>
            <input type="text" name="aggregation_terms" size="{{ len(query.aggregation_terms) }}" value="{{ query.aggregation_terms | e }}" />
            <span class="field-actions">
                <a class="hide remove-filter" title="Remove aggregation on '{{ query.aggregation_terms | e }}'" href="?{{ query.as_params(without_param=("aggregation_terms", query.aggregation_terms)) }}">🗑</a>
            </span>
        </span>
        <input type="text" name="aggregation_size" hidden value="{{ query.aggregation_size | e }}" />
    {% endif %}

    {% if query.percentiles_terms %}
        <span class="field-filter">
            <label for="percentiles_terms">percentiles of:</label>
            <input type="text" name="percentiles_terms" title="percentiles of" size="{{ len(query.percentiles_terms) }}" value="{{ query.percentiles_terms | e }}" />

            <input type="text" name="percentiles" title="percentiles" size="{{ len(query.percentiles_str) }}" value="{{ query.percentiles_str | e }}" />

            <span class="field-actions">
                <a class="hide remove-filter" title="Remove percentiles of '{{ query.percentiles_terms | e }}'" href="?{{ query.as_params(without_param=("percentiles_terms", query.percentiles_terms)) }}">🗑</a>
            </span>
        </span>
    {% endif %}

        <span class="meta">
            <input type="text" name="from" title="from" size="{{ len(query.from_timestamp)-1 }}" value="{{ query.from_timestamp | e }}" />
            <input type="text" name="to" title="to" size="{{ len(query.to_timestamp)-1 }}" value="{{ query.to_timestamp | e }}" />

            <input type="text" name="interval" title="interval" size="2" value="{{ query.interval | e }}" autocomplete="on" list="intervals" />
            <datalist id="intervals">
                <option value="auto">auto</option>
                <option value="30s">30s</option>
                <option value="1m">1m</option>
                <option value="15m">15m</option>
                <option value="1h">1h</option>
            </datalist>

            <select name="sort" title="sort order">
    {% for sort_order, selected in sort_orders.items() %}
                <option value="{{ sort_order | e }}" {% if selected %}selected{% endif %}>{{ sort_order | e }}</option>
    {% endfor %}
            </select>
        </span>

        <input type="submit" value="Update" />
    </form>
{% endblock query_form %}

<section class="stats">
    <p><span id="stats-num-hits">0 results</span></p>
</section>

<div id="histogram_container">
    <span id="histogram_links">
        <a rel="noreferrer" href="{{ aggregation_url }}" title="Render query as image">↬</a>
    </span>

    <object id="histogram" type="image/svg+xml" alt="Visualization of log entries" data="{{ aggregation_url }}"></object>
</div>

<script src="/static/enhance.js" defer async></script>

<table class="results">
<thead>
<tr>
    <td></td>
{% for field, remove_link in fields.items() %}
    <td class="field" data-class="field-{{ field }}">{{ field }} <a class="remove-link" href="{{ remove_link }}">✖</a></td>
{% endfor %}
</tr>
</thead>

<tbody>
""")
        fields = {}
        for field in self.query.fields:
            escaped_field = escape(field)
            remove_query = copy.copy(self.query)
            remove_query.fields_original = ",".join(filter(lambda f: f != field, self.query.fields))
            fields[escaped_field] = remove_query.as_url('/logs')

        datacenters = {}
        for datacenter in self.config.endpoints.keys():
            datacenters[datacenter] = datacenter == self.query.datacenter

        sort_orders = {}
        for order in ["asc", "desc"]:
            sort_orders[order] = order == self.query.sort

        return template.render(map=map, str=str, len=len, min=min, aggregation_url=aggregation_url, fields=fields, datacenters=datacenters, query=self.query, indices=self.config.indices, sort_orders=sort_orders)

    def num_results(self, results_total, took_ms, took_es_ms):
        """ Render info about number of results. """

        return f"""<tr id="num-results" data-results-total="{results_total}" data-took-ms="{took_ms}" data-took-es-ms="{took_es_ms}"></tr>"""

    def result(self, hit, source):
        """ Renders a single result. """

        fields = {}
        for field in self.query.fields:
            val = escape(source.get(field, ''))

            if field == "_source":
                source = json.dumps(hit['_source'])
                val = f"<div class=\"source-flattened\">{escape(source)}</div>"
                fields[field] = val
                continue

            if field in self.config.field_format and val:
                fmt = self.config.field_format[field]
                val = FieldFormatter().format(fmt, __query=self.query.as_params(),
                                              dc=self.query.datacenter, index=self.query.index,
                                              **hit['_source'])
            if field not in source:
                val = '-'
            elif source.get(field, '') is None:
                val = 'null'
            fields[field] = val

        formatted_fields = {}
        for field, fmt_str in self.config.field_format.items():
            try:
                val = nested_get(hit['_source'], field.split("."))
                if val:
                    fmt = self.config.field_format[field]
                    val = FieldFormatter().format(fmt, __query=self.query.as_params(),
                                                  dc=self.query.datacenter, index=self.query.index,
                                                  **hit['_source'])
                    formatted_fields[field] = val
            except (IndexError, KeyError, ValueError):
                pass

        template = Template(r"""
<tr class="row" data-source="{{ source_json | e }}" data-formatted-fields="{{ formatted_fields | e }}">
    <td class="toggle-expand"{% if aggregation_color %} style="border-left: 0.5ex solid {{ aggregation_color }}; padding-left: 0.5ex;"{% endif %}>+</td>
{% for field, val in fields.items() %}
    <td data-field="{{ field | e }}" class="field-{{ field | e }}">
        <span class="field-container">{{ val }}</span>
        <a class="filter filter-include" title="Filter for results matching value" href="#">🔎</a>
        <a class="filter filter-exclude" title="Exclude results matching value" href="#">🗑</a>
    </td>
{% endfor %}
</tr>
<tr class="source source-hidden"><td colspan="{{ 1 + len_fields }}"></td></tr>
""")
        source_with_meta = hit['_source']
        source_with_meta['_id'] = hit['_id']
        source_with_meta['_index'] = hit['_index']
        aggregation_color = None
        if self.query.aggregation_terms:
            try:
                val = nested_get(hit['_source'], self.query.aggregation_terms.removesuffix('.keyword').split('.'))
                aggregation_color = self.color_mapper.to_color(val)
            except (IndexError, KeyError, ValueError):
                pass
        return template.render(source_json=json.dumps(source_with_meta), len_fields=len(self.query.fields),
                               fields=fields, formatted_fields=json.dumps(formatted_fields),
                               aggregation_color=aggregation_color)

    def end(self):
        """ Renders end of results. """
        return """</tbody>
</table>
</body>
</html>"""

    def warning(self, msg, es_query):
        """ Render warning. """

        return self.__notice("warning", es_query, msg)

    def error(self, ex, es_query):
        """ Render error. """

        if isinstance(ex, elasticsearch.ConnectionTimeout):
            msg = f"Warning: Connection timeout: {ex} (Check details for query)"
            return self.__notice("warning", es_query, msg)
        else:
            msg = f"ERROR!: {str(ex)}"
            return self.__notice("error", es_query, msg)

    def __notice(self, class_, es_query, msg):
        template = Template(r"""
<tr data-source="{{ es_query_json | e }}">
    <td class="toggle-expand">+</td>
    <td class="{{ class_ }}" colspan="{{ width }}">{{ msg | e }}</td>
<tr class="source source-hidden"><td colspan="{{ 1 + width }}"></td></tr>
""")
        return template.render(es_query_json=json.dumps(es_query), class_=class_, width=len(self.query.fields), msg=msg)


def nested_get(dct, keys):
    """ Gets keys recursively from dict, e.g. nested_get({test: inner: 42}, ["test", "inner"])
        would return the nested `42`. """
    for key in keys:
        if isinstance(dct, list):
            dct = dct[int(key)]
        else:
            dct = dct[key]
    return dct


class FieldFormatter(string.Formatter):
    """ Custom formatter test gets nested dot-separated fields from an object. """

    def get_value(self, key, args, kwargs):
        val = kwargs.get(key)
        if isinstance(val, dict):
            return DotMap(val)
        return escape(val)


class DotMap(dict):
    """ A tiny map that allows key access via ".key" syntax. """

    def __getattr__(self, attr):
        val = self.get(attr)
        if isinstance(val, dict):
            return DotMap(val)
        return escape(val)
