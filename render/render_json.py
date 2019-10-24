""" Handles JSON rendering. """

import json

class JSONRenderer:
    """ Renders JSON output. """

    def __init__(self):
        self.is_first = True

    def start(self):
        return "["

    def num_results(self, results_total, took_ms):
        return ""

    def result(self, hit, source):
        prefix = ", "
        if self.is_first:
            prefix = ""
            self.is_first = False
        return prefix + json.dumps(source)

    def warning(self, msg, es_query):
        return ""

    def error(self, ex, es_query):
        return ""

    def end(self):
        return "]"
