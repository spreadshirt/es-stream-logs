""" Tiny graph library. """

import math

class Scale:
    """ A Scale maps values from an input domain to an output range.

    For example, numbers between 0 and 100 would be mapped to pixels
    from 0 to 300.
    """

    def __init__(self, num_steps: int, domain, range_):
        (domain_min, domain_max) = domain
        (range_min, range_max) = range_

        self.num_steps = num_steps
        self.factor = (range_max - range_min) / (domain_max - domain_min)
        self.domain_min = domain_min

    def map(self, value_in_domain):
        """ Maps value_in_domain to the corresponding value in the
        output range. """
        return (value_in_domain - self.domain_min) * self.factor


E10 = math.sqrt(50)
E5 = math.sqrt(10)
E2 = math.sqrt(2)

def tick_increment(start, stop, count):
    """
    Finds a nice number to step between start and stop for count times.

    Port of d3.array.tickIncrement.  See
    https://github.com/d3/d3-array/blob/36c6ee3593739a2698d04a45d24c70b557ede84c/src/ticks.js#L34-L41.
    """

    step = (stop - start) / max(0, count)
    power = math.floor(math.log10(step))
    error = step / math.pow(10, power)
    multiply = 1
    if error >= E10:
        multiply = 10
    elif error >= E5:
        multiply = 5
    elif error >= E2:
        multiply = 2

    if power >= 0:
        return multiply * math.pow(10, power)
    return -math.pow(10, -power) * multiply

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

TIME_INTERVALS = [
        1, 5, 15, 30, # seconds
        1*MINUTE, 5*MINUTE, 15*MINUTE, 30*MINUTE, # minutes
        1*HOUR, 3*HOUR, 6*HOUR, 12*HOUR, # hours
        1*DAY, 2*DAY, 7*DAY, # days
]

def time_increment(start_s: int, stop_s: int, count: int):
    """ Finds a nice time increment for count steps between start (in
        seconds) and end (in seconds).

        Inspired by the time scale from d3:
        https://github.com/d3/d3-scale/blob/151f2a0517c97adc28317913bd70f94a4176a0d0/src/time.js
    """

    initial_interval = (stop_s - start_s) / count
    for interval in TIME_INTERVALS:
        if initial_interval < interval:
            return interval

    return ValueError("could not find appropriate interval")

def pretty_duration(duration_s: int):
    """ Returns a pretty duration for the one given in seconds, e.g. 1h, 3m, 4d, ..."""
    fmt = ""
    if duration_s < MINUTE:
        fmt = f"{duration_s}s"
    elif duration_s < HOUR:
        fmt = f"{duration_s // MINUTE}m"
    elif duration_s < 24 * HOUR:
        fmt = f"{duration_s // HOUR}h"
    else:
        fmt = f"{duration_s // (24*HOUR)}d"
    return fmt
