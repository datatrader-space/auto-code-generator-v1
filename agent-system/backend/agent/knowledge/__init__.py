# agent/knowledge/__init__.py
"""
Knowledge base module for CRS documentation and context
"""

from .crs_documentation import (
    CRS_DOCUMENTATION,
    get_system_prompt,
    get_crs_documentation_context
)

__all__ = [
    'CRS_DOCUMENTATION',
    'get_system_prompt',
    'get_crs_documentation_context'
]
