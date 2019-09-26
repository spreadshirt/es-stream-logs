""" Tiny graph library. """

import math

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
