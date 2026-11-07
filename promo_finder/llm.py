"""One tiny interface over many LLM providers.

    llm = get_llm("gemini:gemini-2.5-flash")
    text = llm.complete(system, user, json_mode=True)

Model strings are "<provider>:<model>". Supported providers:
    gemini      GEMINI_API_KEY (or GOOGLE_API_KEY)  - free tier at aistudio.google.com (Interactions API)
    openai      OPENAI_API_KEY
    groq        GROQ_API_KEY                         - OpenAI-compatible
    openrouter  OPENROUTER_API_KEY                   - OpenAI-compatible
    ollama      (local, no key)                      - OpenAI-compatible at localhost:11434
    compat      LLM_BASE_URL + LLM_API_KEY           - any other OpenAI-compatible endpoint
    anthropic   ANTHROPIC_API_KEY
    none        no LLM; rules only

Swapping the model is a one-flag change: --model groq:llama-3.3-70b-versatile.
"""
from __future__ import annotations

import json
import os
import re
import time

DEFAULT_MODEL = os.getenv("PROMO_MODEL", "gemini:gemini-3.8-flash")

OPENAI_COMPAT = {
    "openai": (None, "OPENAI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "compat": (os.getenv("LLM_BASE_URL"), "LLM_API_KEY"),
}

# conservative requests/minute so free tiers don't 429 us
DEFAULT_RPM = {"gemini": 9, "groq": 25, "openrouter": 15}


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


class BaseLLM:
    provider = "base"

    def __init__(self, model: str, api_key: str | None = None, temperature: float = 0.4):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        rpm = float(os.getenv("PROMO_RPM", DEFAULT_RPM.get(self.provider, 60)))
        self._min_gap = 60.0 / rpm if rpm > 0 else 0
        self._last = 0.0
        self.calls = 0
        self.notify = lambda msg: print(f"   [llm] {msg}", flush=True)  # pipeline replaces this to reach the UI
        self.max_calls = int(os.getenv("PROMO_MAX_CALLS", "0") or 0)  # 0 = unlimited

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    def spend(self) -> None:
        """Count one real API request; refuse once the budget (PROMO_MAX_CALLS) is used up."""
        if self.max_calls and self.calls >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} reached (PROMO_MAX_CALLS)")
        self.calls += 1

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        # Only rate-limit errors are retried here (after waiting), at most twice. Timeouts / 5xx are NOT
        # retried blindly, because on a metered key every retry costs money; providers with a fallback
        # chain (Gemini) handle those by switching model once.
        for attempt in range(3):
            wait = self._min_gap - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                return self._call(system, user, json_mode)
            except BudgetExceeded:
                raise
            except Exception as e:  # noqa: BLE001 - provider SDKs raise many types
                msg = str(e)
                rate_limited = any(k in msg.lower() for k in ("429", "rate limit", "quota", "exhaust"))
                if not rate_limited or attempt == 2:
                    raise LLMError(f"{self.name}: {msg[:500]}") from e
                m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg) or re.search(r"retryDelay[^0-9]*(\d+)", msg)
                sleep = float(m.group(1)) + 1 if m else 20.0 * (attempt + 1)
                self.notify(f"Rate limit reached, waiting {sleep:.0f}s before trying again")
                time.sleep(sleep)
        raise LLMError("unreachable")

    def _call(self, system: str, user: str, json_mode: bool) -> str:  # pragma: no cover
        raise NotImplementedError


class GeminiLLM(BaseLLM):
    provider = "gemini"

    def __init__(self, model, api_key=None, **kw):
        super().__init__(model, api_key, **kw)
        from google import genai
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)")
        from google.genai import types
        # attempts=1: the SDK otherwise silently retries timeouts/5xx up to 4 more times (each one can be billed
        # and each waits the full timeout). Retrying is decided by us, explicitly, in complete()/_call().
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)))
        self.active = model

    @property
    def name(self) -> str:
        return f"gemini:{self.active}"

    def _call(self, system, user, json_mode):
        # Try the configured model first; if Google times it out (504 / deadline), fall back down the list
        # and stick with whichever model answers, so one overloaded model doesn't stall a 50-episode run.
        chain = [self.model] + [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS",
                                "gemini-3.6-flash,gemini-3.1-flash-lite").split(",") if m.strip()]
        chain = list(dict.fromkeys(chain[chain.index(self.active):] if self.active in chain else chain))
        last = None
        for m in chain:
            try:
                text = self._interact(m, system, user, json_mode)
                if m != self.active:
                    self.notify(f"Now using {m} for the rest of this run")
                    self.active = m
                return text
            except BudgetExceeded:
                raise
            except Exception as e:  # noqa: BLE001
                msg = str(e).lower()
                if not any(k in msg for k in ("timed out", "timeout", "deadline", "504", "503", "unavailable",
                                              "no longer available", "not found", "404")):
                    raise
                self.notify(f"{m} is busy or timed out, switching to the next model")
                last = e
        raise LLMError(f"all Gemini models failed: {last}")

    def _interact(self, model, system, user, json_mode):
        # Interactions API (what Gemini 3.x models are documented with). No google_search tool on purpose:
        # promos must come only from the screenplay, and search would add latency and outside content.
        kw = {"response_format": {"type": "text", "mime_type": "application/json"}} if json_mode else {}
        self.spend()
        r = self.client.interactions.create(
            model=model if model.startswith("models/") else f"models/{model}",
            input=user,
            system_instruction=system,
            generation_config={"max_output_tokens": 65536, "thinking_level": os.getenv("GEMINI_THINKING", "medium"),
                               "temperature": self.temperature},
            timeout=float(os.getenv("GEMINI_TIMEOUT", "90")),
            **kw,
        )
        text = getattr(r, "output_text", None)
        if not text:
            parts = []
            for step in getattr(r, "steps", None) or []:
                for c in getattr(step, "content", None) or []:
                    if getattr(c, "text", None):
                        parts.append(c.text)
            text = "".join(parts)
        if not text:
            raise LLMError(f"empty response (status={getattr(r, 'status', '?')})")
        return text


class OpenAICompatLLM(BaseLLM):
    def __init__(self, provider, model, api_key=None, **kw):
        self.provider = provider
        super().__init__(model, api_key, **kw)
        from openai import OpenAI
        base, env = OPENAI_COMPAT[provider]
        key = api_key or (os.getenv(env) if env else "ollama") or ""
        if not key:
            raise LLMError(f"Set {env} for provider '{provider}'")
        self.client = OpenAI(api_key=key, base_url=base)

    def _call(self, system, user, json_mode):
        kw = {"response_format": {"type": "json_object"}} if json_mode else {}
        self.spend()
        r = self.client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kw)
        return r.choices[0].message.content or ""


class AnthropicLLM(BaseLLM):
    provider = "anthropic"

    def __init__(self, model, api_key=None, **kw):
        super().__init__(model, api_key, **kw)
        import anthropic
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("Set ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=key)

    def _call(self, system, user, json_mode):
        if json_mode:
            user += "\n\nRespond with a single JSON object only."
        self.spend()
        r = self.client.messages.create(model=self.model, max_tokens=8000, system=system,
                                        messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def get_llm(spec: str | None = None, api_key: str | None = None) -> BaseLLM | None:
    spec = (spec or DEFAULT_MODEL).strip()
    if spec.lower() in ("none", "rules", "offline", ""):
        return None
    provider, _, model = spec.partition(":")
    provider = provider.lower()
    if not model:
        raise LLMError(f"model spec must look like 'provider:model', got {spec!r}")
    if provider == "gemini":
        return GeminiLLM(model, api_key)
    if provider == "anthropic":
        return AnthropicLLM(model, api_key)
    if provider in OPENAI_COMPAT:
        return OpenAICompatLLM(provider, model, api_key)
    raise LLMError(f"unknown provider {provider!r}")


def parse_json(text: str):
    """Parse model output that should be JSON, tolerating ``` fences and chatter."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", t, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise
