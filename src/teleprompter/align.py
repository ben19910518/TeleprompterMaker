"""Compatibility import: shared implementation lives in lyric_aligner.align."""
import sys
from lyric_aligner import align as _implementation
sys.modules[__name__] = _implementation
