"""Retired subscription adapter: never exchange OAuth for API billing or local fallback."""
from backend.auth.chatgpt_auth import MIGRATION_MESSAGE


class ChatGPTSubscriptionAdapter:
    def __init__(self, auth_manager):
        self.auth = auth_manager

    def is_available(self) -> bool:
        return False

    def get_cooldown(self):
        return None

    def query_local_ollama(self, messages, fallback_model=None):
        raise ValueError(MIGRATION_MESSAGE)

    def chat(self, model, messages, timeout=60.0, allow_fallback=False):
        raise ValueError(MIGRATION_MESSAGE)
