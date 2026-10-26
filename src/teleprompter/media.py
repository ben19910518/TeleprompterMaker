"""Compatibility import: shared implementation lives in lyric_aligner.media."""
import sys
from lyric_aligner import media as _implementation
sys.modules[__name__] = _implementation
