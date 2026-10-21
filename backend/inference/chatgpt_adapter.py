"""ChatGPT Subscription Model Adapter with Intelligent Local Fallback.
Allows chatting with ChatGPT Plus/Pro models (gpt-4o, gpt-4o-mini, o1-mini)
using the OAuth access token.
If ChatGPT hits an hourly limit or 429, it:
1. Records the cooldown and notifies the user.
2. Automatically falls back to a running local model (Ollama) if available.
"""
from __future__ import annotations
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Callable
from backend.auth.chatgpt_auth import ChatGPTAuthManager

LOG = logging.getLogger('axx.chatgpt_adapter')

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OLLAMA_LOCAL_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

class ChatGPTSubscriptionAdapter:
    def __init__(self, auth_manager: ChatGPTAuthManager):
        self.auth = auth_manager
        self.cooldown_until: float = 0
        self.cooldown_message: str | None = None

    def is_available(self) -> bool:
        return self.auth.is_authenticated()

    def get_cooldown(self) -> dict | None:
        remaining = self.cooldown_until - time.time()
        if remaining > 0:
            return {
                "active": True,
                "remaining_seconds": round(remaining),
                "message": self.cooldown_message or f"Límite de ChatGPT alcanzado. Espera {round(remaining)} segundos."
            }
        return None

    def query_local_ollama(self, messages: list[dict], fallback_model: str | None = None) -> dict | None:
        """Attempts to query local Ollama as a fallback."""
        try:
            # First check available models if none provided
            chosen_model = fallback_model
            if not chosen_model:
                req = urllib.request.Request(OLLAMA_TAGS_URL, method='GET')
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    tags = json.loads(resp.read().decode('utf-8'))
                    models = tags.get('models', [])
                    if models:
                        chosen_model = models[0].get('name')
            if not chosen_model:
                return None

            payload = {
                "model": chosen_model,
                "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
                "stream": False
            }
            body_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                OLLAMA_LOCAL_URL,
                data=body_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=40.0) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                content = data.get('message', {}).get('content', '')
                if content:
                    return {
                        "content": content,
                        "model": chosen_model,
                        "provider": "ollama-local-fallback"
                    }
        except Exception as e:
            LOG.warning('Ollama local fallback query failed: %s', e)
        return None

    def chat(self, model: str, messages: list[dict], timeout: float = 60.0, allow_fallback: bool = True) -> dict:
        token = self.auth.get_access_token()
        if not token:
            raise ValueError("No hay una sesión activa de ChatGPT. Conéctate primero desde Ajustes.")

        cooldown = self.get_cooldown()
        if cooldown:
            if allow_fallback:
                local_res = self.query_local_ollama(messages)
                if local_res:
                    return {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": local_res["content"]
                            },
                            "finish_reason": "stop"
                        }],
                        "axx_router": {
                            "provider": "ChatGPT Suscripción (Conmutado a Local)",
                            "model": local_res["model"],
                            "fallback_used": True,
                            "cooldown_notice": cooldown["message"]
                        }
                    }
            raise ValueError(cooldown["message"])

        # Normalize model
        if model not in ("gpt-4o", "gpt-4o-mini", "o1-mini", "chatgpt-auto"):
            model = "gpt-4o"
        actual_model = "gpt-4o" if model == "chatgpt-auto" else model

        payload = {
            "model": actual_model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            "stream": False
        }

        body_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            OPENAI_CHAT_URL,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                choices = data.get('choices', [])
                if not choices:
                    raise ValueError("ChatGPT no devolvió opciones de respuesta válidas.")
                content = choices[0].get('message', {}).get('content', '')
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": content
                        },
                        "finish_reason": "stop"
                    }],
                    "axx_router": {
                        "provider": "ChatGPT Suscripción",
                        "model": actual_model,
                        "fallback_used": False
                    }
                }
        except urllib.error.HTTPError as e:
            raw_err = e.read().decode('utf-8', errors='replace')
            LOG.error('ChatGPT API HTTPError %d: %s', e.code, raw_err)

            if e.code == 401:
                # Token expired, try refreshing
                if self.auth.refresh_access_token():
                    return self.chat(model, messages, timeout, allow_fallback)
                raise ValueError("La sesión de ChatGPT ha expirado. Por favor, vuelve a iniciar sesión.")

            if e.code == 429:
                # Rate limit / usage cap
                retry_after = e.headers.get('Retry-After', '120')
                try:
                    pause = float(retry_after)
                except ValueError:
                    pause = 180.0
                self.cooldown_until = time.time() + pause
                self.cooldown_message = f"Se ha alcanzado temporalmente el límite de tu suscripción de ChatGPT (espera estimada: {round(pause)}s)."

                if allow_fallback:
                    local_res = self.query_local_ollama(messages)
                    if local_res:
                        return {
                            "choices": [{
                                "message": {
                                    "role": "assistant",
                                    "content": local_res["content"]
                                },
                                "finish_reason": "stop"
                            }],
                            "axx_router": {
                                "provider": "ChatGPT Suscripción (Conmutado a Local por límite)",
                                "model": local_res["model"],
                                "fallback_used": True,
                                "cooldown_notice": self.cooldown_message
                            }
                        }
                raise ValueError(self.cooldown_message)

            raise ValueError(f"Error de ChatGPT (HTTP {e.code}): {raw_err[:180]}")
        except Exception as e:
            if allow_fallback:
                local_res = self.query_local_ollama(messages)
                if local_res:
                    return {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": local_res["content"]
                            },
                            "finish_reason": "stop"
                        }],
                        "axx_router": {
                            "provider": "Ollama Local (Fallback por error de conexión)",
                            "model": local_res["model"],
                            "fallback_used": True
                        }
                    }
            raise ValueError(f"Error de conexión con ChatGPT: {e}")
