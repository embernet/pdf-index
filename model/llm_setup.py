"""One-shot setup flow for the optional LLM enrichment layer.

Walks the user from an empty machine to a verified, working LLM:

1. detect the Ollama server
2. pull the configured model if missing
3. run a tiny smoke prompt and validate the response

Each step yields a :class:`SetupEvent` describing progress so a UI dialog can
display a live status log. The final event has ``done=True`` and either
``ok=True`` (everything verified) or ``ok=False`` plus a hint string for what
the user should do next.

This module never raises — every failure surfaces as a SetupEvent. Importing
it on a machine without Ollama is also safe; it just means the first event
will say "Ollama not detected".
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Iterator

from model import llm_client


@dataclass
class SetupEvent:
    """One step in the setup flow.

    Attributes:
        message: Human-readable progress text for the UI log.
        done: True iff this is the final event of the run.
        ok: Only meaningful when ``done`` is True. Whether setup succeeded.
        hint: Only meaningful when ``done`` and not ``ok``. Suggested next action.
    """
    message: str
    done: bool = False
    ok: bool = False
    hint: str = ""


def _install_hint() -> str:
    sysname = platform.system()
    if sysname == "Darwin":
        return ("Install Ollama: `brew install ollama`, then run `ollama serve` "
                "in a terminal — or download from https://ollama.com/download")
    if sysname == "Linux":
        return ("Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh` "
                "and run `ollama serve` — or see https://ollama.com/download")
    return ("Install Ollama from https://ollama.com/download, then start the "
            "Ollama service before retrying setup.")


SMOKE_PROMPT = (
    "Reply with strictly the JSON object {\"ok\": true} and nothing else. "
    "Do not include any prose, code fences, or whitespace before or after."
)


def run_setup(host: str, model: str) -> Iterator[SetupEvent]:
    """Drive the full setup flow, yielding one SetupEvent per step.

    The caller (typically a Qt dialog backed by a worker thread) consumes
    events and updates UI. The last event always has ``done=True``.
    """
    yield SetupEvent(message=f"Checking Ollama server at {host}...")
    if not llm_client.is_available(host):
        yield SetupEvent(
            message="Ollama server not reachable.",
            done=True,
            ok=False,
            hint=_install_hint(),
        )
        return
    yield SetupEvent(message="Server reachable.")

    yield SetupEvent(message=f"Checking whether model '{model}' is present...")
    if llm_client.model_present(model, host):
        yield SetupEvent(message=f"Model '{model}' is already installed.")
    else:
        yield SetupEvent(message=f"Pulling model '{model}'. This may take a while...")
        last_status: list[str] = [""]

        def _on_progress(msg: str) -> None:
            # Don't spam the UI with identical lines — Ollama emits the same
            # status many times during a layer download.
            if msg and msg != last_status[0]:
                last_status[0] = msg
                _yield_buffer.append(msg)

        # We can't yield from inside a callback, so buffer and drain.
        _yield_buffer: list[str] = []
        ok = llm_client.pull_model(model, host, progress_cb=_on_progress)
        for buffered in _yield_buffer:
            yield SetupEvent(message=buffered)
        if not ok:
            yield SetupEvent(
                message=f"Failed to pull model '{model}'.",
                done=True,
                ok=False,
                hint=(f"Verify the model name is correct (try `ollama pull {model}` "
                      "in a terminal). Common alternatives: qwen2.5:7b, llama3.1:8b, "
                      "mistral:7b."),
            )
            return
        yield SetupEvent(message=f"Pulled '{model}' successfully.")

    yield SetupEvent(message="Running smoke test...")
    response = llm_client.complete(
        prompt=SMOKE_PROMPT,
        model=model,
        host=host,
        fmt="json",
        timeout=30,
        use_cache=False,
    )
    if response is None:
        yield SetupEvent(
            message="Smoke test failed: no response from model.",
            done=True,
            ok=False,
            hint=("The model is installed but did not respond. Check the Ollama "
                  "server logs (often visible where you started `ollama serve`)."),
        )
        return
    if not isinstance(response, dict) or response.get("ok") is not True:
        yield SetupEvent(
            message=f"Smoke test returned unexpected response: {response!r}",
            done=True,
            ok=False,
            hint=("The model responded but didn't produce valid JSON. Try a more "
                  "capable model such as qwen2.5:7b or llama3.1:8b."),
        )
        return

    yield SetupEvent(
        message="Smoke test passed. LLM enrichment is ready.",
        done=True,
        ok=True,
    )
