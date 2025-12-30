"""
Custom DRF Renderers
"""
from rest_framework import renderers


class PassthroughRenderer(renderers.BaseRenderer):
    """
    Passthrough renderer for raw responses (like StreamingHttpResponse)

    Use this when you want to return a raw Django response and bypass
    DRF's rendering system entirely.
    """
    media_type = '*/*'
    format = 'txt'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Return data as-is. For StreamingHttpResponse, this is already rendered.
        """
        return data
