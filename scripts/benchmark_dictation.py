"""Offline ASR comparison using the SAME consented corpus; aggregate output only.

python scripts/benchmark_dictation.py --corpus corpus.json --models default parakeet-tdt-0.6b-v3 --output build/phase8/asr.json
Corpus: [{"audio":"relative.wav", "mime":"audio/wav", "language":"es", "expected":"..."}].
No downloads. No audio or reference/hypothesis text is written to the report.
"""
import argparse
import base64
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.speech.offline_asr import OfflineTranscriptionService, MAX_AUDIO
from backend.speech.windows_tts import SpeechError


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1): next_row.append(min(row[j] + 1, next_row[-1] + 1, row[j-1] + (x != y)))
        row = next_row
    return row[-1]


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def percentile(values, p):
    if not values: return None
    return sorted(values)[min(len(values)-1, max(0, int(len(values)*p + .999999)-1))]


def benchmark(corpus_path, selected):
    import psutil
    corpus = json.loads(corpus_path.read_text(encoding='utf-8-sig'))
    if not isinstance(corpus, list) or not 1 <= len(corpus) <= 500: raise ValueError('Corpus requires 1 to 500 entries')
    for sample in corpus:
        if not isinstance(sample, dict) or set(sample) != {'audio', 'mime', 'language', 'expected'} or not isinstance(sample['expected'], str) or not 1 <= len(sample['expected']) <= 8000:
            raise ValueError('Invalid corpus entry')
        path = (corpus_path.parent / sample['audio']).resolve()
        if not path.is_relative_to(corpus_path.parent.resolve()) or not path.is_file() or not 0 < path.stat().st_size <= MAX_AUDIO: raise ValueError('Audio must be bounded and inside the corpus directory')
    report = {'schema':1, 'samples':len(corpus), 'acceptance_corpus':len(corpus) >= 50, 'normalization':'NFC, casefold, whitespace; punctuation and digits preserved', 'models':[]}
    for model in selected:
        with tempfile.TemporaryDirectory() as directory:
            service = OfflineTranscriptionService(directory)
            latencies = []; words = chars = word_errors = char_errors = 0; peaks = [0, 0.0]
            done = threading.Event()
            def monitor():
                while not done.wait(.05):
                    try:
                        worker = service._worker
                        processes = [psutil.Process(worker[0].pid)] if worker else []
                        if processes: processes += processes[0].children(recursive=True)
                        peaks[0] = max(peaks[0], sum(p.memory_info().rss for p in processes))
                        peaks[1] = max(peaks[1], sum(sum(p.cpu_times()[:2]) for p in processes))
                    except (psutil.Error, OSError): pass
            thread = threading.Thread(target=monitor, daemon=True); thread.start()
            result = {'model':model, 'status':'PASS'}
            try:
                for sample in corpus:
                    path = corpus_path.parent / sample['audio']
                    body = {'audio_base64':base64.b64encode(path.read_bytes()).decode(), 'mime':sample['mime'], 'language':sample['language'], 'task':'transcribe'}
                    if model != 'default': body['model'] = model
                    began = time.perf_counter(); response = service.transcribe(body); latencies.append((time.perf_counter()-began)*1000)
                    expected, actual = normalized(sample['expected']), normalized(response['text'])
                    words += len(expected.split()); chars += len(expected)
                    word_errors += distance(expected.split(), actual.split()); char_errors += distance(expected, actual)
                result.update(wer=word_errors/max(1,words), cer=char_errors/max(1,chars), first_ms=latencies[0],
                    warm_p50_ms=statistics.median(latencies[1:]) if len(latencies)>1 else None,
                    warm_p95_ms=percentile(latencies[1:], .95), peak_worker_tree_rss_bytes=peaks[0], worker_tree_cpu_seconds=peaks[1])
            except SpeechError as error: result.update(status='BLOCKED', code=error.code)
            finally: done.set(); thread.join(1); service.close()
            report['models'].append(result)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path); parser.add_argument('--models', nargs='+', default=['default'])
    parser.add_argument('--output', type=Path); parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        assert distance('abc', 'adc') == 1 and distance([], ['a']) == 1
        assert normalized('  ÁXX  1.25 mg ') == 'áxx 1.25 mg'
        assert percentile([3,1,2], .95) == 3
        print('PASS: WER/CER distance, normalization, percentile'); raise SystemExit(0)
    if not args.corpus or not args.output: parser.error('--corpus and --output are required')
    report = benchmark(args.corpus, args.models)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
