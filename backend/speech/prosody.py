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
        'serious':      (0.0, 0.84, 1.07, 0.38, 0.52, 85),
        'analytical':   (0.0, 0.97, 0.99, 0.44, 0.58, 55),
        'affectionate': (0.0, 0.89, 1.04, 0.44, 0.56, 65),
        'reflective':   (0.0, 0.90, 1.03, 0.50, 0.62, 70),
        'intro':        (0.0, 1.02, 0.93, 0.54, 0.66, 45),
        'question':     (0.0, 1.01, 0.94, 0.57, 0.68, 60),
        'excited':      (0.0, 1.05, 0.91, 0.58, 0.70, 50),
        'neutral':      (0.0, 1.00, 0.96, 0.50, 0.65, 50),
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
            # 1. Check if leading discourse intro ("Okay,", "Mira,", "Bueno,") precedes a non-neutral clause
            m_intro = cls.RE_INTRO.match(s)
            if m_intro and m_intro.end() < len(s):
                first = s[:m_intro.end()].strip()
                rest = s[m_intro.end():].strip()
                rest_mood = cls.classify_chunk(rest, idx=1)
                if first and rest and rest_mood != 'neutral':
                    raw_chunks.append(first)
                    s = rest

            # 2. Split on mid-sentence contrast/register pivots ("..., pero ...", "..., vamos a ponernos serios...")
            parts = [p.strip() for p in cls.RE_CONTRAST_PIVOT.split(s) if p and p.strip()]
            if len(parts) > 1:
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
            pause_ms = 35 if (mood == 'neutral' and punct == ',') else base_pause

            # Merge consecutive clauses that share the exact same mood (unless separated by a dramatic pause)
            # so VITS/MOSS preserves long-form neural coarticulation within the same register.
            if (
                clauses
                and clauses[-1].mood == mood
                and mood in ('neutral', 'analytical')
                and len(clauses[-1].text) + len(chunk) <= 220
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
    def pitch_shift_wsola(cls, samples: np.ndarray, sample_rate: int, shift_cents: float) -> np.ndarray:
        """Phase-coherent WSOLA time-pitch shift. Preserves duration while shifting pitch."""
        if abs(shift_cents) < 5.0 or len(samples) < sample_rate * 0.08:
            return samples

        factor = 2.0 ** (shift_cents / 1200.0)
        target_len = max(16, int(len(samples) / factor))
        x_old = np.arange(len(samples), dtype=np.float32)
        x_new = np.linspace(0.0, float(len(samples) - 1), target_len, dtype=np.float32)
        resampled = np.interp(x_new, x_old, samples).astype(np.float32)

        speed = len(resampled) / max(1, len(samples))
        win_size = int(0.020 * sample_rate)
        hop_out = win_size // 2
        hop_in = max(1, int(round(hop_out * speed)))

        window = np.hanning(win_size).astype(np.float32)
        output_len = len(samples)
        output = np.zeros(output_len + win_size, dtype=np.float32)
        weights = np.zeros(output_len + win_size, dtype=np.float32)

        in_pos = 0
        out_pos = 0
        search_range = int(0.006 * sample_rate)

        while out_pos < output_len and in_pos + win_size < len(resampled):
            best_pos = in_pos
            if out_pos > 0 and in_pos >= search_range and in_pos + win_size + search_range < len(resampled):
                ref = output[out_pos:out_pos + win_size]
                best_corr = -1e9
                for delta in range(-search_range, search_range + 1, 2):
                    cand = resampled[in_pos + delta:in_pos + delta + win_size]
                    corr = np.dot(ref, cand)
                    if corr > best_corr:
                        best_corr = corr
                        best_pos = in_pos + delta

            output[out_pos:out_pos + win_size] += resampled[best_pos:best_pos + win_size] * window
            weights[out_pos:out_pos + win_size] += window
            in_pos += hop_in
            out_pos += hop_out

        weights = np.maximum(weights, 1e-4)
        return (output[:output_len] / weights[:output_len]).astype(np.float32)

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
    def apply_vocal_warmth_eq(cls, samples: np.ndarray, sample_rate: int, mood: str = 'neutral') -> np.ndarray:
        """Cascaded Audio EQ Cookbook biquad filters evaluated in pure NumPy FFT: shapes chest warmth and upper-harmonic presence by mood with zero scipy dependency."""
        n = len(samples)
        if n < 128:
            return samples

        try:
            if mood == 'serious':
                # Grounded, authoritative chest depth + darker upper harmonics
                stages = [
                    cls.biquad_peaking(2.8, 195.0, 0.95, sample_rate),
                    cls.biquad_peaking(0.9, 1650.0, 1.1, sample_rate),
                    cls.biquad_peaking(-3.0, 3750.0, 1.25, sample_rate),
                ]
            elif mood == 'analytical':
                # Articulate, clear midrange diction with balanced warmth
                stages = [
                    cls.biquad_peaking(1.4, 215.0, 1.05, sample_rate),
                    cls.biquad_peaking(1.5, 2450.0, 1.1, sample_rate),
                    cls.biquad_peaking(-1.8, 4400.0, 1.35, sample_rate),
                ]
            elif mood == 'affectionate':
                # Close-mic intimate warmth, velvet high-frequency softness
                stages = [
                    cls.biquad_peaking(2.5, 210.0, 1.0, sample_rate),
                    cls.biquad_peaking(-0.6, 2600.0, 1.2, sample_rate),
                    cls.biquad_peaking(-2.8, 4050.0, 1.3, sample_rate),
                ]
            elif mood == 'reflective':
                # Thoughtful, intimate storytelling midrange
                stages = [
                    cls.biquad_peaking(2.1, 205.0, 1.0, sample_rate),
                    cls.biquad_peaking(0.8, 1900.0, 1.15, sample_rate),
                    cls.biquad_peaking(-2.4, 4150.0, 1.35, sample_rate),
                ]
            elif mood in ('intro', 'question', 'excited'):
                # Lively, open presence and conversational brightness
                stages = [
                    cls.biquad_peaking(1.4, 225.0, 1.1, sample_rate),
                    cls.biquad_peaking(1.7, 2400.0, 1.1, sample_rate),
                    cls.biquad_peaking(-1.5, 4600.0, 1.4, sample_rate),
                ]
            else:
                stages = [
                    cls.biquad_peaking(1.8, 225.0, 1.05, sample_rate),
                    cls.biquad_peaking(0.7, 2150.0, 1.1, sample_rate),
                    cls.biquad_peaking(-2.1, 4350.0, 1.4, sample_rate),
                ]

            w = (2.0 * np.pi / float(sample_rate)) * np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
            z1 = np.exp(-1j * w)
            z2 = z1 * z1
            H = np.ones_like(z1, dtype=np.complex128)
            for b, a in stages:
                H *= (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
            filtered = np.fft.irfft(np.fft.rfft(samples) * H, n=n)
            return filtered.astype(np.float32)
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
    def process_clause_pcm(cls, samples: np.ndarray, sample_rate: int, clause: ProsodyClause) -> np.ndarray:
        # 1. Trim VITS boundary dead air so clauses flow together without hesitation gaps
        samples = cls.trim_silence(samples, sample_rate, threshold=0.0045, head_ms=14, tail_ms=20)

        # 2. Optional pitch shift only if explicitly requested (>= 15 cents)
        if abs(clause.pitch_cents) >= 15.0:
            samples = cls.pitch_shift_wsola(samples, sample_rate, clause.pitch_cents)

        # 3. Volume contour
        if abs(clause.volume - 1.0) >= 0.02:
            samples = samples * clause.volume

        # 4. Mood-aware vocal warmth & presence EQ
        samples = cls.apply_vocal_warmth_eq(samples, sample_rate, mood=clause.mood)

        # 5. Anti-click smooth boundary fades (8 ms Hanning)
        fade_len = min(len(samples) // 4, int(0.008 * sample_rate))
        if fade_len > 0:
            hanning_fade = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len, dtype=np.float32) / fade_len))
            samples[:fade_len] *= hanning_fade
            samples[-fade_len:] *= hanning_fade[::-1]

        return samples
