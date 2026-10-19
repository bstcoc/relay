"""Mapping spec: loading and validation."""

from relay_engine.mapping.errors import MappingError
from relay_engine.mapping.loader import load_mapping, load_mappings
from relay_engine.mapping.model import MappingSpec
from relay_engine.mapping.validate import validate_mapping

__all__ = ["MappingError", "MappingSpec", "load_mapping", "load_mappings", "validate_mapping"]
