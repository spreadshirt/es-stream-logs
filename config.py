""" Configuration parsing and definition. """

from dataclasses import dataclass
import json
from typing import Dict

@dataclass
class Endpoint:
    """ Configuration for an elasticsearch endpoint. """

    url: str

@dataclass
class Config:
    """ Encapsulates configuration, e.g. datacenters. """

    default_endpoint: str
    endpoints: Dict[str, Endpoint]

def from_file(filename):
    """ Parse config from YAML in filename. """

    with open(filename, 'r') as fpp:
        return Config(**json.load(fpp))

if __name__ == '__main__':
    CONFIG = from_file('config.json')
    print(CONFIG.endpoints)
