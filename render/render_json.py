""" Handles JSON rendering. """

import json

class JSONRenderer:
    """ Renders JSON output. """

    def start(self):
        return "["

    def result(self, hit, source):
        return json.dumps(source)

    def no_results(self, es_query):
        return ""

    def error(self, ex, es_query):
        return ""

    def end(self):
        return "]"
