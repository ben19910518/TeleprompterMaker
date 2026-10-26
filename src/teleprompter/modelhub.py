"""Compatibility import: shared implementation lives in lyric_aligner.modelhub."""
import sys
from lyric_aligner import modelhub as _implementation
sys.modules[__name__] = _implementation
