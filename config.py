""" Configuration parsing and definition. """

from dataclasses import dataclass
import json
from typing import Dict, List

@dataclass
class Endpoint:
    """ Configuration for an elasticsearch endpoint. """

    url: str

@dataclass
class DefaultFields:
    """ Configuration for default fields. """

    match_params: dict
    fields: List[str]

    def matches(self, kwargs):
        """ Checks if this definition matches the query given in kwargs,
        and returns the assigned fields if so. """

        for key, val in self.match_params.items():
            if key in kwargs and val in kwargs[key]:
                return self.fields
        return None

@dataclass
class Config:
    """ Encapsulates configuration, e.g. datacenters. """

    default_endpoint: str
    endpoints: Dict[str, Endpoint]

    field_format: Dict[str, str]
    default_fields: List[DefaultFields]

    def __post_init__(self):
        for key in self.endpoints:
            self.endpoints[key] = Endpoint(**self.endpoints[key])
        self.default_fields = [DefaultFields(**df) for df in self.default_fields]

    def find_default_fields(self, **kwargs):
        """ Finds default fields defined for query in config.

        Returns None if no matching default fields were found. """

        for default_fields in self.default_fields:
            fields = default_fields.matches(kwargs)
            if fields:
                return fields.copy()
        return None

def from_file(filename):
    """ Parse config from YAML in filename. """

    with open(filename, 'r') as fpp:
        return Config(**json.load(fpp))

if __name__ == '__main__':
    CONFIG = from_file('config.json')
    print(CONFIG.endpoints)
    print(CONFIG.default_fields)
