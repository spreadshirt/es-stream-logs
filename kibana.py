import re
from urllib.parse import unquote, urlparse

import requests


def parse(kibana_url: str):
    """ Parses a Kibana url into an es-stream-logs one. """

    if "/goto/" in kibana_url:
        resp = requests.head(kibana_url, allow_redirects=True)
        resp.raise_for_status()

        kibana_url = resp.url

    kibana_url = urlparse(kibana_url)
    kibana_query = unquote(kibana_url.fragment)
    print(kibana_query)

    timestamp = re.search(r"from:([^,]+),(mode:[^,]+,)?to:([^,)]+)", kibana_query)
    from_timestamp = timestamp[1] if timestamp else 'now-15m'
    to_timestamp = timestamp[3] if timestamp else 'now'

    interval = re.search(r"interval:([^,]+)", kibana_query)
    if not interval:
        raise Exception("missing interval")
    interval = interval[1]

    # columns:!(application_name,level,message)
    fields = re.search(r"columns:!\(([\w+,]+)\)", kibana_query)
    if fields:
        fields = fields[1]
    if fields == "_source":
        fields = None

    # index:'application-*'
    index = re.search(r"index:'?([^,'\"]+)'?", kibana_query)
    if not index:
        raise Exception("missing index", index)
    index = index[1]
    if "-*" not in index:
        kibana_base = kibana_url.scheme + "://" + kibana_url.netloc
        resp = requests.get(kibana_base + "/api/saved_objects/index-pattern/" + index)
        resp.raise_for_status()

        index = resp.json()['attributes']['title']

    args = []

    # query:(match:(level:(query:ERROR,type:phrase)))
    #   ["match", ["level", ["query:ERROR,type:phrase"]]]
    # query:(match:(application_name:(query:api,type:phrase)))
    #   ["match", ["application_name", ["query:api,type:phrase"]]]
    # query:(match_all:())
    # query:(match:(geoip.as_number:(query:'34989',type:phrase)))
    # query:(language:lucene,query:'')
    query_marker = "query:("
    idx = 0
    try:
        while True:
            idx = kibana_query.index(query_marker, idx)
            idx += len(query_marker) - 1

            depth, query = parse_parentheses(kibana_query[idx:])
            print(idx, depth, query)
            if depth == 3:
                if query[0] == "match":
                    var_name = query[1][0]
                    query_spec = dict(map(lambda e: [e[0], e[1].strip("'")], [x.split(":", 2) for x in query[1][1][0].split(",")]))
                    if 'query' not in query_spec:
                        raise Exception(f'no query for "{var_name}"')

                    args.append(f"{var_name}={query_spec['query']}")
    except ValueError:
        pass

    url = f"index={index}&from={from_timestamp}&to={to_timestamp}&interval={interval}"
    if len(args) > 0:
        url += "&" + "&".join(args)
    if fields:
        url += f"&fields=@timestamp,{fields}"
    return url


def push(obj, levels, depth):
    while depth > 0:
        levels = levels[-1]
        depth -= 1

    if isinstance(obj, str) and obj[-1] == ":":
        obj = obj[:-1]
    levels.append(obj)


def parse_parentheses(s):
    groups = []
    depth = 0
    max_depth = 0

    group = ""
    try:
        for ch in s:
            if ch == '(':
                if group != "":
                    push(group, groups, depth)
                    group = ""

                push([], groups, depth)
                depth += 1
                max_depth = max(depth, max_depth)
            elif ch == ')':
                if group != "":
                    push(group, groups, depth)
                    group = ""
                depth -= 1
                if depth == 0:
                    return max_depth, groups[0]

            else:
                group += ch
    except IndexError:
        pass

    if depth > 0:
        raise ValueError('parentheses mismatch')
    else:
        return max_depth, groups[0]


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print("parse", arg)
        try:
            res = parse(arg)
            print(res)
        except Exception as ex:
            print(ex)
