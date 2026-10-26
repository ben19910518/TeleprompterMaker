"""Preview playback with a sample-accurate clock.

The decoded song is played through PortAudio (sounddevice). The clock used by
the preview is derived from the samples actually handed to the sound card
plus the device latency, so lyrics on screen line up with what you hear.
Without a usable output device it falls back to a silent wall clock.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:  # PortAudio missing: preview still works, silently
    sd = None


class AudioPlayer:
    def __init__(self):
        self.sr = 48000
        self.data: Optional[np.ndarray] = None   # int16 (n, 2)
        self.duration = 0.0
        self._stream = None
        self._lock = threading.Lock()
        self._idx = 0
        self._anchor = None            # (perf_counter at DAC, sample index)
        self._playing = False
        self._silent_t0 = None         # wall-clock fallback
        self._silent_pos = 0.0
        self.volume = 1.0
        self.error = ""

    # ---------------------------------------------------------------- data
    def set_audio(self, data: Optional[np.ndarray], sr: int = 48000) -> None:
        self.stop()
        if data is None:
            self.data = None
            self.duration = 0.0
            return
        self.sr = sr
        self.data = np.ascontiguousarray((np.clip(data, -1, 1) * 32767).astype(np.int16))
        self.duration = len(self.data) / sr

    def set_duration(self, seconds: float) -> None:
        """For playback without audio data (silent clock)."""
        if self.data is None:
            self.duration = seconds

    # ------------------------------------------------------------- control
    @property
    def playing(self) -> bool:
        return self._playing

    def play(self, t: float) -> None:
        self.stop()
        t = max(0.0, min(t, max(0.0, self.duration - 0.01)))
        self._playing = True
        if self.data is not None and sd is not None:
            try:
                with self._lock:
                    self._idx = int(t * self.sr)
                    self._anchor = None
                self._play_t = t
                self._stream = sd.OutputStream(samplerate=self.sr, channels=2, dtype="int16",
                                               callback=self._callback, finished_callback=self._finished)
                self._stream.start()
                self.error = ""
                return
            except Exception as e:  # no device, exclusive mode, ...
                self.error = str(e)
                self._stream = None
        self._silent_pos = t
        self._silent_t0 = time.perf_counter()

    def stop(self) -> None:
        pos = self.position() if self._playing else None
        self._playing = False
        st = self._stream
        self._stream = None
        if st is not None:
            try:
                st.abort()
                st.close()
            except Exception:
                pass
        if pos is not None:
            self._silent_pos = pos
        self._silent_t0 = None

    def position(self) -> float:
        if not self._playing:
            return self._silent_pos
        if self._stream is None:
            if self._silent_t0 is None:
                return self._silent_pos
            return min(self.duration, self._silent_pos + time.perf_counter() - self._silent_t0)
        with self._lock:
            anchor = self._anchor
            idx = self._idx
        if anchor is None:
            return self._play_t
        t_dac, sample = anchor
        pos = (sample + (time.perf_counter() - t_dac) * self.sr) / self.sr
        return max(0.0, min(pos, idx / self.sr, self.duration))

    @property
    def finished(self) -> bool:
        return self._playing and self.position() >= self.duration - 0.02

    # ------------------------------------------------------------ callback
    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            i = self._idx
            chunk = self.data[i:i + frames]
            n = len(chunk)
            if self.volume != 1.0:
                outdata[:n] = (chunk * self.volume).astype(np.int16)
            else:
                outdata[:n] = chunk
            if n < frames:
                outdata[n:] = 0
            self._idx = i + n
            try:
                lat = time_info.outputBufferDacTime - time_info.currentTime
                if not (0 <= lat < 1.0):
                    raise ValueError
            except Exception:
                lat = self._stream.latency if self._stream is not None else 0.05
            self._anchor = (time.perf_counter() + lat, i)
        if n < frames:
            raise sd.CallbackStop()

    def _finished(self):
        pass
