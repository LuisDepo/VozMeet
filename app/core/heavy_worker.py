"""
Isolated worker for the GPU/Metal-heavy pipeline stage.

Run as:  python -m app.core.heavy_worker <wav_path> <out_json> [--no-diarize]

Transcription (mlx / faster-whisper) and diarization (pyannote, optionally on
Metal/MPS) both touch C-extensions that can abort() the whole process on some
machines (notably certain M1 configs). Running them here, in a child process,
means such a crash returns a non-zero exit code instead of killing the main
VozMeet app — the parent can then disable the offending accelerator and retry
on CPU.

Live transcription progress is streamed to stdout as "PROGRESS <frac>" lines.
The final result (transcript + diarization) is written as JSON to <out_json>.
"""
import sys
import json
import concurrent.futures


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: heavy_worker <wav_path> <out_json> [--no-diarize]\n")
        return 2
    wav_path, out_json = sys.argv[1], sys.argv[2]
    no_diarize = "--no-diarize" in sys.argv

    from app.core.transcriber import transcribe

    def _progress(frac: float):
        try:
            sys.stdout.write("PROGRESS %.4f\n" % float(frac))
            sys.stdout.flush()
        except Exception:
            pass

    if no_diarize:
        # Transcription only — never imports torch/pyannote, always works.
        transcript = transcribe(wav_path, None, _progress)
        diarization = []
    else:
        from app.core.diarizer import diarize
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            future_tx = ex.submit(transcribe, wav_path, None, _progress)
            future_di = ex.submit(diarize, wav_path)
            transcript = future_tx.result()
            diarization = future_di.result()

    with open(out_json, "w") as f:
        json.dump({"transcript": transcript, "diarization": diarization}, f)

    sys.stdout.write("DONE\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
