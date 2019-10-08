""" Handles JSON rendering. """

import json

class JSONRenderer:
    """ Renders JSON output. """

    def start(self, datacenter, index, fields, query_args):
        return "["

    def result(self, dc, index, fields, hit, source, to_timestamp):
        return json.dumps(source)

    def no_results(self, query, fields):
        return ""

    def error(self, query, fields, ex):
        return ""

    def end(self):
        return "]"
