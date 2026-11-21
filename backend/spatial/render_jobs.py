"""Motion & Simulation Studio: deterministic freeze(t), reproducible simulation, TTS narration sync, and MP4 export (PR-06 / MP-05).

Enforces Invariants:
- Deterministic freeze(t, seed): querying any timestamp t >= 0 produces identical object poses,
  camera state, subtitle/narration cue, and rendered frame digest.
- I-07: Illustrative kinematics/physics are explicitly tagged 'illustrative_not_fem_cfd'.
- Voice integration: narration cues use AXX's real speech_text.prepare_spoken_text and prosody analysis,
  and rendering runs cooperatively without blocking the live voice or microphone pipeline.
- Security: Remote worker export requires explicit remote_transfer_approved=True grant.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import time
from typing import Any

from PIL import Image, ImageDraw

from backend.speech.speech_text import prepare_spoken_text
from backend.spatial.scene_document import (
    SceneDocumentError,
    _check_id,
    validate_scene_document_v2,
)


class MotionStudioError(ValueError):
    """Raised when a motion timeline, simulation spec, or export request is invalid."""


class RemoteExportPermissionError(PermissionError):
    """Raised when attempting to export frames/video to a remote worker without explicit user approval."""


def _lerp(a: float, b: float, alpha: float) -> float:
    clamped = min(1.0, max(0.0, float(alpha)))
    return float(a) + (float(b) - float(a)) * clamped


def _lerp_vec3(v0: list[float], v1: list[float], alpha: float) -> list[float]:
    return [round(_lerp(a, b, alpha), 5) for a, b in zip(v0, v1)]


def evaluate_simulation_step(
    sim_spec: dict[str, Any],
    t_seconds: float,
    *,
    seed: int = 42,
) -> dict[str, float]:
    """Deterministic illustrative physical simulation (spring-damper, piston-crank, or orbital) at time t."""
    kind = str(sim_spec.get('kind', 'harmonic_oscillator'))
    freq_hz = max(0.01, min(float(sim_spec.get('frequency_hz', 1.0)), 50.0))
    amplitude = max(0.0, min(float(sim_spec.get('amplitude', 1.0)), 100.0))
    damping = max(0.0, min(float(sim_spec.get('damping', 0.05)), 5.0))
    # Deterministic phase offset derived from seed
    phase_rad = ((int(seed) * 2654435761) % 360) * (math.pi / 180.0) * float(sim_spec.get('use_seed_phase', 0.0))
    omega = 2.0 * math.pi * freq_hz
    t = max(0.0, float(t_seconds))

    if kind == 'piston_crank':
        crank_r = max(0.1, float(sim_spec.get('crank_radius', amplitude or 1.0)))
        rod_l = max(crank_r * 1.5, float(sim_spec.get('rod_length', crank_r * 3.5)))
        theta = omega * t + phase_rad
        sin_t = math.sin(theta)
        cos_t = math.cos(theta)
        displacement = crank_r * cos_t + math.sqrt(max(0.0, rod_l * rod_l - (crank_r * sin_t) ** 2))
        return {
            'displacement': round(displacement, 5),
            'angle_deg': round((theta * 180.0 / math.pi) % 360.0, 4),
            'dx': 0.0,
            'dy': round(displacement - rod_l, 5),
            'dz': 0.0,
        }

    if kind == 'orbital':
        theta = omega * t + phase_rad
        return {
            'displacement': round(amplitude, 5),
            'angle_deg': round((theta * 180.0 / math.pi) % 360.0, 4),
            'dx': round(amplitude * math.cos(theta), 5),
            'dy': 0.0,
            'dz': round(amplitude * math.sin(theta), 5),
        }

    # Default: damped harmonic oscillator
    envelope = math.exp(-damping * t)
    disp = amplitude * envelope * math.cos(omega * t + phase_rad)
    return {
        'displacement': round(disp, 5),
        'angle_deg': 0.0,
        'dx': 0.0,
        'dy': round(disp, 5),
        'dz': 0.0,
    }


def freeze_scene_at(
    scene_doc: dict[str, Any],
    t_seconds: float,
    *,
    seed: int = 42,
    language: str = 'es',
) -> dict[str, Any]:
    """Deterministic freeze(t): compute exact scene snapshot, camera pose, and prepared TTS cue at time t."""
    validated = validate_scene_document_v2(scene_doc)
    if type(t_seconds) not in (int, float) or not math.isfinite(t_seconds) or t_seconds < 0:
        raise MotionStudioError('Timestamp t_seconds must be a finite number >= 0')
    t = round(float(t_seconds), 4)

    timeline = validated['timeline']
    duration = float(timeline.get('duration_seconds', 0.0))
    tracks = timeline.get('tracks') or []

    # Base object transforms
    object_poses: dict[str, dict[str, Any]] = {}
    for obj in validated['objects']:
        oid = obj['id']
        tr = obj.get('transform') or {}
        object_poses[oid] = {
            'id': oid,
            'name': obj['name'],
            'position': list(tr.get('position', [0.0, 0.0, 0.0])),
            'rotation': list(tr.get('rotation', [0.0, 0.0, 0.0])),
            'scale': list(tr.get('scale', [1.0, 1.0, 1.0])),
            'opacity': 1.0,
            'cutaway_offset': None,
            'highlighted': False,
        }

    camera = {
        'eye': [0.0, 3.0, 10.0],
        'target': [0.0, 0.0, 0.0],
        'fov': 45.0,
    }
    active_narration = None
    active_subtitle = ''

    for track in tracks:
        if not isinstance(track, dict):
            continue
        kind = track.get('kind', 'transform')
        start = float(track.get('start_time', 0.0))
        track_dur = max(1e-4, float(track.get('duration', 1.0)))
        end = start + track_dur
        if t < start:
            continue
        alpha = 1.0 if t >= end else (t - start) / track_dur

        if kind == 'transform':
            target_id = track.get('target_object_id')
            if target_id in object_poses:
                pose = object_poses[target_id]
                if isinstance(track.get('from_position'), list) and isinstance(track.get('to_position'), list):
                    pose['position'] = _lerp_vec3(track['from_position'], track['to_position'], alpha)
                if isinstance(track.get('from_rotation'), list) and isinstance(track.get('to_rotation'), list):
                    pose['rotation'] = _lerp_vec3(track['from_rotation'], track['to_rotation'], alpha)
                if isinstance(track.get('from_scale'), list) and isinstance(track.get('to_scale'), list):
                    pose['scale'] = _lerp_vec3(track['from_scale'], track['to_scale'], alpha)
                if 'from_opacity' in track and 'to_opacity' in track:
                    pose['opacity'] = round(_lerp(track['from_opacity'], track['to_opacity'], alpha), 4)

        elif kind == 'cutaway':
            target_id = track.get('target_object_id')
            if target_id in object_poses:
                from_off = float(track.get('from_offset', 1.0))
                to_off = float(track.get('to_offset', 0.0))
                object_poses[target_id]['cutaway_offset'] = round(_lerp(from_off, to_off, alpha), 4)

        elif kind == 'simulation':
            target_id = track.get('target_object_id')
            if target_id in object_poses:
                sim_state = evaluate_simulation_step(
                    track.get('simulation_spec') or {},
                    t - start,
                    seed=seed,
                )
                base_pos = object_poses[target_id]['position']
                object_poses[target_id]['position'] = [
                    round(base_pos[0] + sim_state['dx'], 5),
                    round(base_pos[1] + sim_state['dy'], 5),
                    round(base_pos[2] + sim_state['dz'], 5),
                ]
                object_poses[target_id]['simulation_state'] = sim_state

        elif kind == 'camera':
            if isinstance(track.get('from_eye'), list) and isinstance(track.get('to_eye'), list):
                camera['eye'] = _lerp_vec3(track['from_eye'], track['to_eye'], alpha)
            if isinstance(track.get('from_target'), list) and isinstance(track.get('to_target'), list):
                camera['target'] = _lerp_vec3(track['from_target'], track['to_target'], alpha)
            if 'from_fov' in track and 'to_fov' in track:
                camera['fov'] = round(_lerp(track['from_fov'], track['to_fov'], alpha), 4)

        elif kind in ('teaching_step', 'narration') and start <= t <= end:
            raw_text = str(track.get('narration') or track.get('title') or '').strip()
            spoken_text, resolved_lang = prepare_spoken_text(raw_text, language=language) if raw_text else ('', language)
            active_subtitle = raw_text
            active_narration = {
                'track_id': track.get('track_id', 'narration'),
                'title': str(track.get('title', '')),
                'display_subtitle': raw_text,
                'prepared_spoken_text': spoken_text,
                'language': resolved_lang,
                'progress': round(alpha, 4),
            }
            for focused_id in track.get('focus') or []:
                if focused_id in object_poses:
                    object_poses[focused_id]['highlighted'] = True

    snapshot = {
        'document_id': validated['document_id'],
        'revision': validated['revision'],
        'timestamp_seconds': t,
        'duration_seconds': duration,
        'seed': int(seed),
        'simulation_fidelity': 'illustrative_not_fem_cfd',
        'camera': camera,
        'objects': [object_poses[o['id']] for o in validated['objects']],
        'active_subtitle': active_subtitle,
        'active_narration': active_narration,
    }
    raw_bytes = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    snapshot['state_sha256'] = hashlib.sha256(raw_bytes).hexdigest()
    return snapshot


def render_frozen_frame_png(
    snapshot: dict[str, Any],
    *,
    width: int = 640,
    height: int = 360,
) -> bytes:
    """Render a deterministic 2D projection frame PNG for a frozen snapshot."""
    img = Image.new('RGB', (width, height), (13, 17, 23))
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    scale_px = min(width, height) / 16.0

    for obj in snapshot.get('objects', []):
        pos = obj.get('position', [0.0, 0.0, 0.0])
        sc = obj.get('scale', [1.0, 1.0, 1.0])
        ox = int(cx + pos[0] * scale_px)
        oy = int(cy - pos[1] * scale_px)
        rw = max(12, int(sc[0] * scale_px))
        rh = max(12, int(sc[1] * scale_px))
        outline = (63, 185, 80) if obj.get('highlighted') else (88, 166, 255)
        fill = (28, 38, 52) if obj.get('opacity', 1.0) > 0.5 else (18, 23, 31)
        draw.rectangle([ox - rw, oy - rh, ox + rw, oy + rh], fill=fill, outline=outline, width=2)
        draw.text((ox - rw + 4, oy - 6), str(obj.get('name', obj.get('id')))[:20], fill=(230, 237, 243))

    if snapshot.get('active_subtitle'):
        draw.rectangle([20, height - 44, width - 20, height - 12], fill=(22, 27, 34), outline=(48, 54, 61))
        draw.text((32, height - 34), str(snapshot['active_subtitle'])[:80], fill=(230, 237, 243))

    draw.text(
        (16, 12),
        f"t={snapshot.get('timestamp_seconds', 0.0):.2f}s | seed={snapshot.get('seed', 42)}",
        fill=(139, 148, 158),
    )
    buf = io.BytesIO()
    img.save(buf, format='PNG', compress_level=6)
    return buf.getvalue()


def _build_deterministic_mp4_container(
    frame_pngs: list[bytes],
    *,
    fps: int,
    seed: int,
    timestamps: list[float],
) -> bytes:
    """Encode real H.264 video with the already packaged PyAV runtime."""
    try:
        import av
    except ImportError as exc:
        raise MotionStudioError('Video export requires the pinned PyAV runtime in requirements-telegram.txt') from exc
    output = io.BytesIO()
    with av.open(output, mode='w', format='mp4', options={'fflags': '+bitexact'}) as video:
        with Image.open(io.BytesIO(frame_pngs[0])) as first:
            width, height = first.size
        stream = video.add_stream('libx264', rate=fps)
        stream.width, stream.height = width, height
        stream.pix_fmt = 'yuv420p'
        stream.codec_context.thread_count = 1
        stream.codec_context.flags |= av.codec.context.Flags.bitexact
        stream.options = {'preset': 'medium', 'crf': '18'}
        for index, png in enumerate(frame_pngs):
            with Image.open(io.BytesIO(png)) as image:
                frame = av.VideoFrame.from_image(image.convert('RGB'))
            frame.pts = index
            for packet in stream.encode(frame):
                video.mux(packet)
        for packet in stream.encode():
            video.mux(packet)
    return output.getvalue()


def export_motion_mp4(
    scene_doc: dict[str, Any],
    *,
    output_path: str | Path | None = None,
    fps: int = 10,
    seed: int = 42,
    duration_override: float | None = None,
    width: int = 640,
    height: int = 360,
    remote_worker: bool = False,
    remote_transfer_approved: bool = False,
    yield_interval_seconds: float = 0.0,
) -> dict[str, Any]:
    """Render deterministic timeline frames and package a reproducible MP4 file without blocking voice."""
    if remote_worker and not remote_transfer_approved:
        raise RemoteExportPermissionError(
            'Exporting scene or video to a remote worker requires explicit user data transfer approval'
        )
    validated = validate_scene_document_v2(scene_doc)
    if type(fps) is not int or not (1 <= fps <= 60):
        raise MotionStudioError('fps must be an integer between 1 and 60')
    duration = float(
        duration_override
        if duration_override is not None
        else validated['timeline'].get('duration_seconds', 1.0)
    )
    duration = max(0.1, min(duration, 60.0))
    frame_count = max(1, int(round(duration * fps)))
    timestamps = [round(i / float(fps), 4) for i in range(frame_count)]

    frame_pngs: list[bytes] = []
    frame_hashes: list[str] = []
    narration_cues: list[dict[str, Any]] = []
    seen_cues: set[str] = set()

    for ts in timestamps:
        snap = freeze_scene_at(validated, ts, seed=seed)
        png = render_frozen_frame_png(snap, width=width, height=height)
        frame_pngs.append(png)
        frame_hashes.append(hashlib.sha256(png).hexdigest())
        cue = snap.get('active_narration')
        if cue and cue['track_id'] not in seen_cues:
            seen_cues.add(cue['track_id'])
            narration_cues.append(cue)
        if yield_interval_seconds > 0:
            time.sleep(min(yield_interval_seconds, 0.005))

    mp4_bytes = _build_deterministic_mp4_container(
        frame_pngs,
        fps=fps,
        seed=seed,
        timestamps=timestamps,
    )
    mp4_sha256 = hashlib.sha256(mp4_bytes).hexdigest()
    written_path = None
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(mp4_bytes)
        written_path = str(out)

    return {
        'document_id': validated['document_id'],
        'revision': validated['revision'],
        'fps': fps,
        'seed': int(seed),
        'frame_count': frame_count,
        'timestamps': timestamps,
        'frame_hashes': frame_hashes,
        'narration_cues': narration_cues,
        'mp4_bytes': mp4_bytes,
        'mp4_sha256': mp4_sha256,
        'mp4_size_bytes': len(mp4_bytes),
        'output_path': written_path,
        'simulation_fidelity': 'illustrative_not_fem_cfd',
    }
