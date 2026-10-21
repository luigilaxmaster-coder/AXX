# API providers and local model configuration — 2026-10-21

Implemented connections for Ollama, LM Studio, Groq, Anthropic Messages, OpenRouter, OpenAI, Gemini, and custom OpenAI/Anthropic-compatible endpoints. Base URLs accept loopback and private IPs over HTTP; Internet endpoints require HTTPS. Models can be discovered or entered explicitly. Configurations can be edited/disabled, with connection-specific selection persisted across restarts.

Credentials are handled in the backend, encrypted with Windows DPAPI, excluded from public configuration responses, and never stored in browser preferences. Empty key fields preserve existing credentials. A connection cannot silently reuse its stored key on a different endpoint. The legacy save-key route uses this same storage path.

Fixed a routing bug that ignored the selected model. Requests now carry the selected connection and model into the inference worker. No automatic switch to another connection occurs when one has been explicitly selected. Fixed Ollama's empty `data: null` catalog response.

The user requested paid-capable API platforms including Claude. The global `allow_paid` setting remains false; an explicit per-connection quota/balance authorization permits that connection. Paid providers are not marked as free merely because a key was supplied. No real external inference or purchase was performed.

## Verification

- `python -m unittest discover -s backend/tests -q`: 53 passed.
- `python -m unittest discover -s backend/inference/tests -q`: 17 passed.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: 18 browser/IPC contract groups passed.
- `node 1.AXX/scripts/test-chat-usability.cjs`: 7 groups passed.
- `node 1.AXX/scripts/test-providers.cjs`: presets, discovery, save/edit/disable, selected connection, key clearing, no browser persistence, and custom protocol passed.
- `backend/tests/verify_provider_packaged.py`: actual frozen executable started; model discovery, protected configuration, redacted listing, DPAPI encryption, and inference through a frozen worker passed against a loopback fixture. See `packaged-verification.json`.
- Actual installed Ollama was reached through the new discovery code and returned an empty catalog, correctly interpreted as no installed models.
- `git diff --check`: passed before delivery.

Review was self-review, not an independent audit. Browser and frozen-worker tests do not prove authenticated cloud-provider availability or generation performance of an uninstalled model. No physical Windows UI automation was attempted in this turn.

## Hardware and recommendation

Confirmed via CIM and nvidia-smi: Core i7-14700KF, 31.8 GiB RAM, RTX 3050 with 8192 MiB VRAM. About 5446 MiB VRAM was free at inspection. Ollama 0.32.3 was installed, with no models. Recommend starting with Qwen3 4B Q4_K_M; Qwen3.5 4B and Qwen3 8B are alternatives with less memory headroom. No models downloaded. See `docs/PROVEEDORES-API-LOCAL.md` for sources and setup.

Delivery: native Tauri build completed successfully; all three backend binary copies have the verified SHA-256. Axx restarted with PID 51920. Exact executable and source hashes are in build-receipt.json.
