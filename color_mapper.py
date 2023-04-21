import random


class ColorMapper():
    """ Maps values to colors, consistently. """

    def __init__(self):
        self.map = {}
        self.static_map = {
            "2xx": "green",
            "3xx": "lightgreen",
            "4xx": "yellow",
            "5xx": "red",
            "info": "green",
            "warn": "yellow",
            "warning": "yellow",
            "error": "red",
        }

    def to_color(self, value):
        """ Maps the given value to a color. """

        if isinstance(value, int):
            # special case for guessed http statuses
            if 200 <= value < 300:
                value = "2xx"
            elif 300 <= value < 400:
                value = "3xx"
            elif 400 <= value < 500:
                value = "4xx"
            elif 500 <= value < 600:
                value = "5xx"

        if not isinstance(value, str):
            value = str(value)

        if value.lower() in self.static_map:
            return self.static_map[value.lower()]

        if value not in self.map:
            rnd = random.Random(value)
            random_color = f"hsl({rnd.randint(0, 360)}, 90%, 50%)"
            self.map[value] = random_color

        return self.map[value]
