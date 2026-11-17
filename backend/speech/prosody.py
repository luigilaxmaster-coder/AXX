"""Dynamic Prosody & Context-Aware Humanization Engine for Axx Speech Services.

Provides:
1. Semantic, emotional, and communicative-intent clause analysis across 8 human vocal registers:
   - serious (firm, grounded, lower volume, deeper chest resonance, deliberate pace)
   - analytical (clear, didactic, articulate midrange, steady pace)
   - affectionate (warm, close-mic intimacy, velvet high-shelf roll-off, gentle pace)
   - reflective (thoughtful, hushed storytelling/aside, warm midrange, measured pauses)
   - excited (energetic, bright presence, faster pace, fuller projection)
   - question (curious, upward-inflected variability, open presence)
   - intro (conversational discourse pivot, crisp attack, micro-pause before shift)
   - neutral (fluid, natural conversational baseline)
2. Contrast & pivot splitting so multi-idea sentences shift voice naturally mid-utterance
   while consecutive same-mood clauses merge for seamless neural continuity.
3. Pure-NumPy FFT cascaded biquad EQ and silence trimming (zero scipy dependency).
"""
from __future__ import annotations

import re
import numpy as np


class ProsodyClause:
    __slots__ = ('text', 'mood', 'pitch_cents', 'volume', 'length_factor', 'pause_ms', 'noise_scale', 'noise_w')

    def __init__(
        self,
        text: str,
        mood: str,
        pitch_cents: float,
        volume: float,
        length_factor: float,
        pause_ms: int,
        noise_scale: float = 0.50,
        noise_w: float = 0.65,
    ):
        self.text = text
        self.mood = mood
        self.pitch_cents = pitch_cents
        self.volume = volume
        self.length_factor = length_factor
        self.pause_ms = pause_ms
        self.noise_scale = noise_scale
        self.noise_w = noise_w

    def __repr__(self) -> str:
        return (
            f"<Clause '{self.text}' mood={self.mood} vol={self.volume:.2f} "
            f"len={self.length_factor:.2f} noise={self.noise_scale:.2f} pause={self.pause_ms}ms>"
        )


class ProsodyAnalyzer:
    RE_SERIOUS = re.compile(
        r'\b(vamos a ponernos serios|ponernos serios|hablemos en serio|poni[eé]ndonos serios|'
        r'en serio|hablando en serio|fuera de broma|sin bromas|esto es serio|esto es muy serio|'
        r'esto es importante|es muy importante|esc[uú]chame bien|pon atenci[oó]n|presta atenci[oó]n|'
        r'atenci[oó]n|hablemos claro|de verdad|muy en serio|ten cuidado|mucho cuidado|cuidado con|'
        r'ojo con esto|te lo digo en serio|peligro|advertencia|urgente|cr[ií]tico|error cr[ií]tico|'
        r'no hagas eso|bajo ninguna circunstancia|la verdad es que|siendo honestos|sin rodeos|'
        r'punto clave|fundamental)\b',
        re.I
    )
    RE_INTRO = re.compile(
        r'^(okay|okey|ok|a ver|bueno|mira|oye|bien|perfecto|entendido|d[eé]jame ver|veamos|vale|'
        r'entonces|ahora bien|por cierto|f[ií]jate que|escucha)[,]?\s*',
        re.I
    )
    RE_AFFECTION = re.compile(
        r'\b(amor|mi amor|amorcito|axxmorcito|cielo|coraz[oó]n|cari[nñ]o|beb[eé]|'
        r'tranquil[oa]|no te preocupes|todo va a estar bien|todo saldr[aá] bien|'
        r'aqu[ií] estoy|estoy contigo|estoy aqu[ií] para ti|te entiendo|te comprendo|'
        r'te quiero|te adoro|con calma|respira|descansa|suave|lamento mucho|lo siento mucho|'
        r'perd[oó]n|disculpa|cu[eé]ntame|me alegra escucharte)\b',
        re.I
    )
    RE_ANALYTICAL = re.compile(
        r'\b(por ejemplo|es decir|en otras palabras|primero|en primer lugar|segundo|tercero|'
        r'adem[aá]s|sin embargo|no obstante|por lo tanto|en conclusi[oó]n|en resumen|'
        r'analicemos|te explico|explico|funciona as[ií]|el motivo es|la raz[oó]n es|'
        r't[eé]cnicamente|arquitectura|algoritmo|configuraci[oó]n|par[aá]metro|c[oó]digo|'
        r'sistema|proceso|paso a paso|estructura|implementaci[oó]n|verificaci[oó]n)\b',
        re.I
    )
    RE_REFLECTIVE = re.compile(
        r'(\.\.\.|…|\b(?:imag[ií]nate|pi[eé]nsalo as[ií]|curiosamente|entre nosotros|'
        r'te cuento un secreto|alguna vez|en el fondo|a veces|quiz[aá]s|tal vez|'
        r'es curioso|me pregunto|si lo piensas)\b)',
        re.I
    )
    RE_EXCITE = re.compile(
        r'([!¡]|\b(?:genial|excelente|incre[ií]ble|maravilloso|vamos all[aá]|fant[aá]stico|'
        r'espectacular|brutal|qu[eé] bien|buen[ií]sim[oa]|perfecto|lo logramos|funcion[oó]|'
        r'listo|felicidades|enhorabuena|me encanta|s[uú]per|s[ií] que s[ií]|claro que s[ií]|'
        r'guau|wow)\b)',
        re.I
    )
    RE_CONTRAST_PIVOT = re.compile(
        r'(?:,\s+|\s+)(?=(?:pero|aunque|sin embargo|no obstante|ahora bien|eso s[ií]|'
        r'vamos a ponernos serios|en serio|hablando en serio|esc[uú]chame bien|ten cuidado|'
        r'tranquil[oa]|no te preocupes|por ejemplo|es decir|te explico)\b)',
        re.I
    )

    MOOD_PROFILES = {
        # (pitch_cents, volume, length_factor, noise_scale, noise_w, base_pause_ms)
        # pitch_cents=0.0 preserves 100% pure neural VITS/MOSS phase without WSOLA graininess;
        # low noise_scale (0.34-0.42) & natural length_factor (0.98-1.06) keep consonants crisp.
        'serious':      (0.0, 0.87, 1.06, 0.34, 0.48, 165),
        'analytical':   (0.0, 0.98, 1.02, 0.36, 0.50, 120),
        'affectionate': (0.0, 0.91, 1.04, 0.35, 0.48, 145),
        'reflective':   (0.0, 0.92, 1.04, 0.36, 0.50, 155),
        'intro':        (0.0, 1.01, 0.99, 0.38, 0.52, 85),
        'question':     (0.0, 1.01, 1.01, 0.40, 0.54, 130),
        'excited':      (0.0, 1.04, 0.98, 0.42, 0.56, 115),
        'neutral':      (0.0, 1.00, 1.02, 0.36, 0.50, 125),
    }

    MOOD_CONTOURS = {
        # Normalized clause positions (0..1) -> expressive delta cents layered over base pitch_cents.
        # Coupled with phase-coherent single-voice prosodic warping & syllabic stress inflection.
        'serious':      ((0.0, 0.25, 0.65, 1.0), (-15.0, -5.0, -45.0, -75.0)),
        'analytical':   ((0.0, 0.22, 0.68, 1.0), (22.0, 18.0, -16.0, -45.0)),
        'affectionate': ((0.0, 0.28, 0.65, 1.0), (14.0, 26.0, -12.0, -38.0)),
        'reflective':   ((0.0, 0.30, 0.72, 1.0), (10.0, -8.0, -32.0, -58.0)),
        'intro':        ((0.0, 0.35, 0.78, 1.0), (18.0, 32.0, 14.0, 36.0)),
        'question':     ((0.0, 0.22, 0.58, 0.88, 1.0), (24.0, -6.0, -18.0, 82.0, 74.0)),
        'excited':      ((0.0, 0.26, 0.64, 1.0), (28.0, 62.0, 22.0, -16.0)),
        'neutral':      ((0.0, 0.20, 0.62, 1.0), (22.0, 18.0, -14.0, -48.0)),
    }

    @classmethod
    def classify_chunk(cls, chunk: str, idx: int = 0) -> str:
        stripped = chunk.strip()
        lower = stripped.lower()
        if not stripped:
            return 'neutral'

        is_intro = bool(cls.RE_INTRO.fullmatch(stripped)) or (
            bool(cls.RE_INTRO.match(lower)) and idx == 0 and len(stripped) <= 22
        )
        if is_intro and not cls.RE_SERIOUS.search(lower):
            return 'intro'
        if cls.RE_SERIOUS.search(lower):
            return 'serious'
        if cls.RE_AFFECTION.search(lower):
            return 'affectionate'
        if '?' in stripped or lower.startswith(('¿', 'qué ', 'cómo ', 'cuál ', 'cuándo ', 'por qué ', 'dónde ', 'quién ')):
            return 'question'
        if '!' in stripped or cls.RE_EXCITE.search(lower):
            return 'excited'
        if cls.RE_REFLECTIVE.search(lower):
            return 'reflective'
        if cls.RE_ANALYTICAL.search(lower):
            return 'analytical'
        return 'neutral'

    @classmethod
    def detect_mood(cls, text: str) -> str:
        """Returns the dominant communicative mood of a phrase or sentence."""
        clauses = cls.segment(text)
        if not clauses:
            return 'neutral'
        # Priority order if multiple moods appear in a phrase
        priority = ('serious', 'affectionate', 'excited', 'question', 'reflective', 'analytical', 'intro', 'neutral')
        present = {c.mood for c in clauses}
        for m in priority:
            if m in present:
                return m
        return clauses[0].mood

    @classmethod
    def segment(cls, text: str) -> list[ProsodyClause]:
        clean = text.strip()
        if not clean:
            return []

        # Split on sentence boundaries: . ; : ! ?
        sentences = [s.strip() for s in re.split(r'(?<=[.;:!?])\s+', clean) if s.strip()]
        if not sentences:
            sentences = [clean]

        raw_chunks: list[str] = []
        for s in sentences:
            # 1. Check if leading discourse intro ("Okay,", "Mira,", "Bueno,") precedes a serious/dramatic clause
            m_intro = cls.RE_INTRO.match(s)
            if m_intro and m_intro.end() < len(s):
                first = s[:m_intro.end()].strip()
                rest = s[m_intro.end():].strip()
                rest_mood = cls.classify_chunk(rest, idx=1)
                if first and rest and (rest_mood == 'serious' or cls.RE_SERIOUS.search(rest)):
                    raw_chunks.append(first)
                    s = rest

            # 2. Split on mid-sentence contrast/register pivots only for serious shifts or long multi-clause sentences
            parts = [p.strip() for p in cls.RE_CONTRAST_PIVOT.split(s) if p and p.strip()]
            if len(parts) > 1 and (cls.RE_SERIOUS.search(s) or (len(s) > 110 and all(len(p) >= 28 for p in parts))):
                for p in parts:
                    raw_chunks.append(p)
            else:
                # Also check if RE_SERIOUS starts mid-clause without a conjunction
                m_ser = cls.RE_SERIOUS.search(s)
                if m_ser and m_ser.start() > 2:
                    before = s[:m_ser.start()].strip().rstrip(',')
                    after = s[m_ser.start():].strip()
                    if before and after:
                        raw_chunks.append(before)
                        raw_chunks.append(after)
                        continue
                if s:
                    raw_chunks.append(s)

        clauses: list[ProsodyClause] = []

        for idx, chunk in enumerate(raw_chunks):
            punct = chunk[-1] if chunk[-1] in ',.;:!?' else ''
            mood = cls.classify_chunk(chunk, idx=idx)
            pitch_cents, volume, length_factor, noise_scale, noise_w, base_pause = cls.MOOD_PROFILES.get(
                mood, cls.MOOD_PROFILES['neutral']
            )
            pause_ms = 65 if (mood == 'neutral' and punct == ',') else (80 if punct == ',' else base_pause)

            # Merge consecutive clauses that share the exact same mood (unless separated by a dramatic pause)
            # so VITS/MOSS preserves long-form neural coarticulation within the same register.
            if (
                clauses
                and clauses[-1].mood == mood
                and mood in ('neutral', 'analytical', 'affectionate', 'question')
                and len(clauses[-1].text) + len(chunk) <= 240
            ):
                clauses[-1].text = f"{clauses[-1].text} {chunk}".strip()
                clauses[-1].pause_ms = pause_ms
            else:
                clauses.append(
                    ProsodyClause(
                        chunk, mood, pitch_cents, volume, length_factor, pause_ms,
                        noise_scale=noise_scale, noise_w=noise_w
                    )
                )

        return clauses


class HumanizerDSP:
    @staticmethod
    def biquad_peaking(gain_db: float, f0: float, q: float, fs: int) -> tuple[np.ndarray, np.ndarray]:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * f0 / fs
        alpha = np.sin(w0) / (2.0 * q)
        b0 = 1.0 + alpha * A
        b1 = -2.0 * np.cos(w0)
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * np.cos(w0)
        a2 = 1.0 - alpha / A
        return np.array([b0, b1, b2], dtype=np.float32) / a0, np.array([a0, a1, a2], dtype=np.float32) / a0

    @classmethod
    def pitch_shift_wsola(
        cls,
        samples: np.ndarray,
        sample_rate: int,
        shift_cents: float,
        contour: tuple[tuple[float, ...], tuple[float, ...]] | None = None,
    ) -> np.ndarray:
        """Phase-coherent WSOLA time-pitch shift with optional intonation contour.

        Preserves exact phrase duration while shifting fundamental pitch and
        applying natural phrase-level intonation inflection.
        """
        if (abs(shift_cents) < 5.0 and contour is None) or len(samples) < int(sample_rate * 0.08):
            return samples

        n = len(samples)
        win_size = max(128, int(0.020 * sample_rate))
        hop_out = win_size // 2
        pad_tail = int(win_size * 1.6) + hop_out
        padded = np.concatenate([samples, np.zeros(pad_tail, dtype=np.float32)])
        n_pad = len(padded)

        u = np.linspace(0.0, 1.0, n, dtype=np.float64)
        if contour is not None:
            pts_u, pts_dc = contour
            delta_cents = np.interp(u, pts_u, pts_dc)
        else:
            delta_cents = np.zeros(n, dtype=np.float64)
        curve_n = np.clip(shift_cents + delta_cents, -350.0, 350.0)
        if pad_tail > 0:
            curve = np.concatenate([curve_n, np.full(pad_tail, float(curve_n[-1]), dtype=np.float64)])
        else:
            curve = curve_n

        inv_factor = 1.0 / (2.0 ** (curve / 1200.0))
        t_of_x = np.empty(n_pad, dtype=np.float64)
        t_of_x[0] = 0.0
        t_of_x[1:] = np.cumsum(0.5 * (inv_factor[:-1] + inv_factor[1:]))
        total_res = max(win_size + 16, int(round(t_of_x[-1])))
        res_t = np.arange(total_res + 1, dtype=np.float64)
        x_at_res_t = np.interp(res_t, t_of_x, np.arange(n_pad, dtype=np.float64))
        # Catmull-Rom 4-point cubic spline interpolation preserves high-frequency vocal crispness
        idx1 = np.clip(np.floor(x_at_res_t).astype(np.int64), 0, n_pad - 1)
        t = (x_at_res_t - idx1).astype(np.float32)
        idx0 = np.clip(idx1 - 1, 0, n_pad - 1)
        idx2 = np.clip(idx1 + 1, 0, n_pad - 1)
        idx3 = np.clip(idx1 + 2, 0, n_pad - 1)
        p0, p1, p2, p3 = padded[idx0], padded[idx1], padded[idx2], padded[idx3]
        t2 = t * t
        t3 = t2 * t
        resampled = (
            0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
        ).astype(np.float32)

        window = np.hanning(win_size).astype(np.float32)
        output = np.zeros(n + win_size, dtype=np.float32)
        weights = np.zeros(n + win_size, dtype=np.float32)

        search_range = int(0.005 * sample_rate)
        sliding = getattr(np.lib.stride_tricks, 'sliding_window_view', None)
        res_len = len(resampled)
        out_pos = 0

        while out_pos < n:
            nom_in = int(round(t_of_x[min(out_pos, n_pad - 1)]))
            if nom_in + win_size > res_len:
                break
            best_pos = nom_in
            low = max(0, nom_in - search_range)
            high = min(res_len - win_size, nom_in + search_range)
            if out_pos > 0 and high > low + 4:
                ref = output[out_pos:out_pos + win_size]
                if sliding is not None:
                    cands = sliding(resampled[low:high + win_size], win_size)[::2]
                    if len(cands):
                        corrs = cands @ ref
                        best_pos = low + int(np.argmax(corrs)) * 2
                else:
                    best_corr = -1e9
                    for pos in range(low, high + 1, 2):
                        corr = float(np.dot(ref, resampled[pos:pos + win_size]))
                        if corr > best_corr:
                            best_corr = corr
                            best_pos = pos

            output[out_pos:out_pos + win_size] += resampled[best_pos:best_pos + win_size] * window
            weights[out_pos:out_pos + win_size] += window
            out_pos += hop_out

        weights = np.maximum(weights[:n], 1e-4)
        return (output[:n] / weights).astype(np.float32)

    @staticmethod
    def trim_silence(
        samples: np.ndarray,
        sample_rate: int,
        threshold: float = 0.0045,
        head_ms: int = 16,
        tail_ms: int = 24,
    ) -> np.ndarray:
        """Removes excess VITS/ONNX leading and trailing dead air while preserving natural consonant attacks and releases."""
        if len(samples) < int(sample_rate * 0.12):
            return samples
        win = max(64, int(0.010 * sample_rate))
        abs_s = np.abs(samples)
        active = np.where(abs_s > threshold)[0]
        if len(active) < 16:
            return samples
        head_pad = int(head_ms * sample_rate / 1000.0)
        tail_pad = int(tail_ms * sample_rate / 1000.0)
        start = max(0, int(active[0]) - head_pad)
        end = min(len(samples), int(active[-1]) + tail_pad + win // 2)
        if end - start < int(sample_rate * 0.06):
            return samples
        return samples[start:end].copy()

    @classmethod
    def apply_vocal_warmth_eq(
        cls,
        samples: np.ndarray,
        sample_rate: int,
        mood: str = 'neutral',
        engine: str = 'piper',
    ) -> np.ndarray:
        """Cascaded Audio EQ Cookbook biquad filters evaluated in pure NumPy FFT.

        For Piper VITS (`engine='piper'`), reshapes chest fundamental (+3.3 dB @ 155 Hz),
        tames boxy midrange (-2.2 dB @ 470 Hz) and metallic nasal peak (-3.3 dB @ 1850 Hz)
        to align with the user's measured reference voice envelope.
        For MOSS (`engine='moss'`), applies light mastering polish only.
        """
        n = len(samples)
        if n < 128:
            return samples

        try:
            if engine == 'moss':
                if mood == 'serious':
                    stages = [
                        cls.biquad_peaking(1.1, 165.0, 0.9, sample_rate),
                        cls.biquad_peaking(-1.4, 4200.0, 1.2, sample_rate),
                    ]
                elif mood in ('affectionate', 'reflective'):
                    stages = [
                        cls.biquad_peaking(1.0, 185.0, 0.95, sample_rate),
                        cls.biquad_peaking(-1.3, 4000.0, 1.2, sample_rate),
                    ]
                elif mood in ('analytical', 'excited', 'question', 'intro'):
                    stages = [
                        cls.biquad_peaking(0.7, 210.0, 1.0, sample_rate),
                        cls.biquad_peaking(0.9, 2400.0, 1.1, sample_rate),
                        cls.biquad_peaking(-0.8, 5200.0, 1.3, sample_rate),
                    ]
                else:
                    stages = [
                        cls.biquad_peaking(0.7, 175.0, 0.95, sample_rate),
                        cls.biquad_peaking(-0.9, 4600.0, 1.3, sample_rate),
                    ]
            else:
                # Transparent, natural spectral polish for Piper ONNX
                stages = [
                    cls.biquad_peaking(1.8, 165.0, 0.85, sample_rate),
                    cls.biquad_peaking(-1.5, 480.0, 1.05, sample_rate),
                    cls.biquad_peaking(-1.3, 1880.0, 0.90, sample_rate),
                    cls.biquad_peaking(-0.6, 4200.0, 1.15, sample_rate),
                ]
                if mood == 'serious':
                    stages.extend([
                        cls.biquad_peaking(0.9, 150.0, 0.90, sample_rate),
                        cls.biquad_peaking(-1.0, 3600.0, 1.20, sample_rate),
                    ])
                elif mood == 'analytical':
                    stages.append(cls.biquad_peaking(0.9, 2500.0, 1.20, sample_rate))
                elif mood == 'affectionate':
                    stages.extend([
                        cls.biquad_peaking(0.7, 180.0, 0.95, sample_rate),
                        cls.biquad_peaking(-1.1, 3500.0, 1.15, sample_rate),
                    ])
                elif mood == 'reflective':
                    stages.append(cls.biquad_peaking(-0.8, 3600.0, 1.20, sample_rate))
                elif mood in ('intro', 'question', 'excited'):
                    stages.append(cls.biquad_peaking(1.0, 2450.0, 1.10, sample_rate))

            w = (2.0 * np.pi / float(sample_rate)) * np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
            z1 = np.exp(-1j * w)
            z2 = z1 * z1
            H = np.ones_like(z1, dtype=np.complex128)
            for b, a in stages:
                H *= (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
            filtered = np.fft.irfft(np.fft.rfft(samples) * H, n=n).astype(np.float32)
            peak = float(np.max(np.abs(filtered))) if len(filtered) else 0.0
            if peak > 0.92:
                filtered = np.tanh(filtered * (0.90 / peak)).astype(np.float32) * (peak if peak < 0.98 else 0.95)
            return filtered
        except Exception:
            return samples

    @staticmethod
    def create_comfort_pause(duration_ms: int, sample_rate: int) -> np.ndarray:
        """Natural comfort ambience floor (-68 dBFS) to prevent abrupt silence dropouts."""
        n = int(duration_ms * sample_rate / 1000.0)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        return np.random.normal(0.0, 5e-5, n).astype(np.float32)

    @classmethod
    def _syllabic_stress_envelope(cls, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """Extracts zero-phase 1.2-5.5 Hz syllabic stress modulation envelope in [-1, 1]."""
        n = len(samples)
        if n < 256:
            return np.zeros(n, dtype=np.float32)
        env = np.abs(samples).astype(np.float32)
        freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
        spec = np.fft.rfft(env)
        # Smooth band-pass between 1.0 Hz and 5.5 Hz (human syllable stress rate)
        low_cut = 1.0 / (1.0 + (1.0 / np.maximum(freqs, 1e-3)) ** 4)
        high_cut = 1.0 / (1.0 + (freqs / 5.5) ** 4)
        mod = np.fft.irfft(spec * low_cut * high_cut, n=n).astype(np.float32)
        scale = float(np.percentile(np.abs(mod), 92)) if n > 0 else 0.0
        if scale > 1e-4:
            mod = np.tanh(mod / (scale * 1.15)).astype(np.float32)
        else:
            mod = np.zeros(n, dtype=np.float32)
        return mod

    @classmethod
    def apply_natural_intonation_warp(
        cls,
        samples: np.ndarray,
        sample_rate: int,
        mood: str = 'neutral',
        base_cents: float = 0.0,
        u_start: float = 0.0,
        u_end: float = 1.0,
    ) -> np.ndarray:
        """Single-voice phase-coherent cubic Catmull-Rom prosodic pitch & cadence warp.

        Couples phrase-level intonation contours (question rise, attack peak,
        declarative declination + prepausal lengthening) with syllabic stress
        micro-inflection without WSOLA overlap-add windowing artifacts.
        """
        n = len(samples)
        if n < int(sample_rate * 0.10):
            return samples

        u = np.linspace(float(u_start), float(u_end), n, dtype=np.float64)
        pts_u, pts_dc = ProsodyAnalyzer.MOOD_CONTOURS.get(mood, ProsodyAnalyzer.MOOD_CONTOURS['neutral'])
        macro_cents = np.interp(u, pts_u, pts_dc)

        syl_mod = cls._syllabic_stress_envelope(samples, sample_rate).astype(np.float64)
        syl_cents = 26.0 * syl_mod

        total_cents = np.clip(base_cents + macro_cents + syl_cents, -95.0, 95.0)
        inst_rate = 2.0 ** (total_cents / 1200.0)

        # Cumulative source phase trajectory tau(k)
        t_of_x = np.empty(n, dtype=np.float64)
        t_of_x[0] = 0.0
        t_of_x[1:] = np.cumsum(0.5 * (1.0 / inst_rate[:-1] + 1.0 / inst_rate[1:]))
        out_len = max(64, int(round(t_of_x[-1])))
        out_grid = np.linspace(0.0, t_of_x[-1], out_len, dtype=np.float64)
        src_pos = np.interp(out_grid, t_of_x, np.arange(n, dtype=np.float64))

        idx1 = np.clip(np.floor(src_pos).astype(np.int64), 0, n - 1)
        t = (src_pos - idx1).astype(np.float32)
        idx0 = np.clip(idx1 - 1, 0, n - 1)
        idx2 = np.clip(idx1 + 1, 0, n - 1)
        idx3 = np.clip(idx1 + 2, 0, n - 1)
        p0, p1, p2, p3 = samples[idx0], samples[idx1], samples[idx2], samples[idx3]
        t2 = t * t
        t3 = t2 * t
        warped = (
            0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
        ).astype(np.float32)
        return warped

    @classmethod
    def apply_dynamic_timbre_contour(
        cls,
        samples: np.ndarray,
        sample_rate: int,
        mood: str = 'neutral',
        u_start: float = 0.0,
        u_end: float = 1.0,
    ) -> np.ndarray:
        """Modulates vocal timbre (chest warmth vs upper-harmonic projection) and micro-dynamics."""
        n = len(samples)
        if n < 256:
            return samples
        try:
            u = np.linspace(float(u_start), float(u_end), n, dtype=np.float32)
            pts_u, pts_dc = ProsodyAnalyzer.MOOD_CONTOURS.get(mood, ProsodyAnalyzer.MOOD_CONTOURS['neutral'])
            macro_norm = (np.interp(u, pts_u, pts_dc) / 80.0).astype(np.float32)
            syl_mod = cls._syllabic_stress_envelope(samples, sample_rate)
            expr = np.clip(0.55 * syl_mod + 0.45 * macro_norm, -1.0, 1.0)

            w = (2.0 * np.pi / float(sample_rate)) * np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
            z1 = np.exp(-1j * w)
            z2 = z1 * z1
            spec = np.fft.rfft(samples)

            # Projected upper-mid presence filter (+3.4 dB @ 2450 Hz) for stressed/rising zones
            b_p, a_p = cls.biquad_peaking(3.4, 2450.0, 0.95, sample_rate)
            H_pres = (b_p[0] + b_p[1] * z1 + b_p[2] * z2) / (a_p[0] + a_p[1] * z1 + a_p[2] * z2)
            pres_sig = np.fft.irfft(spec * H_pres, n=n).astype(np.float32)

            # Warm chest resonance filter (+3.2 dB @ 175 Hz, -2.0 dB @ 3100 Hz) for falling/intimate zones
            b_c1, a_c1 = cls.biquad_peaking(3.2, 175.0, 0.85, sample_rate)
            b_c2, a_c2 = cls.biquad_peaking(-2.0, 3100.0, 1.05, sample_rate)
            H_chest = (
                ((b_c1[0] + b_c1[1] * z1 + b_c1[2] * z2) / (a_c1[0] + a_c1[1] * z1 + a_c1[2] * z2))
                * ((b_c2[0] + b_c2[1] * z1 + b_c2[2] * z2) / (a_c2[0] + a_c2[1] * z1 + a_c2[2] * z2))
            )
            chest_sig = np.fft.irfft(spec * H_chest, n=n).astype(np.float32)

            pos_w = np.maximum(0.0, expr) * 0.55
            neg_w = np.maximum(0.0, -expr) * 0.55
            base_w = 1.0 - pos_w - neg_w
            blended = base_w * samples + pos_w * pres_sig + neg_w * chest_sig

            # Subtle human breath-pressure micro-dynamics (+0.7 dB on stress, -0.9 dB on cadence tail)
            dyn_gain = 1.0 + 0.085 * expr
            return (blended * dyn_gain).astype(np.float32)
        except Exception:
            return samples

    @classmethod
    def process_clause_pcm(cls, samples: np.ndarray, sample_rate: int, clause: ProsodyClause) -> np.ndarray:
        # 1. Trim VITS boundary dead air while preserving natural consonant attacks and releases
        samples = cls.trim_silence(samples, sample_rate, threshold=0.0040, head_ms=18, tail_ms=28)

        # 2. Phase-coherent human intonation contour + syllabic stress pitch inflection
        samples = cls.apply_natural_intonation_warp(
            samples, sample_rate, mood=clause.mood, base_cents=clause.pitch_cents
        )

        # 3. Dynamic vocal timbre modulation (projected presence on peaks, warm chest on cadences)
        samples = cls.apply_dynamic_timbre_contour(samples, sample_rate, mood=clause.mood)

        # 4. Volume contour
        if abs(clause.volume - 1.0) >= 0.02:
            samples = samples * clause.volume

        # 5. Mood-aware vocal warmth & spectral match EQ
        samples = cls.apply_vocal_warmth_eq(samples, sample_rate, mood=clause.mood, engine='piper')

        # 6. Anti-click smooth boundary fades (10 ms Hanning)
        fade_len = min(len(samples) // 4, int(0.010 * sample_rate))
        if fade_len > 0:
            hanning_fade = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len, dtype=np.float32) / fade_len))
            samples[:fade_len] *= hanning_fade
            samples[-fade_len:] *= hanning_fade[::-1]

        return samples
