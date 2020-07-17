""" Handles rendering of results. """

from .render_html import HTMLRenderer
from .render_json import JSONRenderer

__all__ = [HTMLRenderer, JSONRenderer]
