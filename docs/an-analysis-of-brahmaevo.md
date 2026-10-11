# An Analysis of BrahmaEvo

**Repository analyzed:** [Brahma-Echo](https://github.com/titechprabhasolutions/Brahma-Echo) (the project is named “Brahma Echo” in its source; “BrahmaEvo” is retained here as requested).

**Source snapshot:** `main` at commit [`2439ebf5df27e10420962fa091ecb75677dfdca9`](https://github.com/titechprabhasolutions/Brahma-Echo/commit/2439ebf5df27e10420962fa091ecb75677dfdca9), dated 2026-09-20. This is a source-code review, not a live reliability benchmark; later commits may differ.

## Executive summary

Brahma Echo has several recovery layers that can make it *feel* more reliable than a one-request screenshot app:

1. Its normal conversational path uses a long-lived Gemini Live session and reconnects after disconnects.
2. Its direct text fallback can try Gemini first and then OpenRouter.
3. Its OpenRouter client walks a sizeable model pool, allows two attempts per model, and temporarily skips models that return HTTP 429.
4. The normal screen-capture path sends a much smaller JPEG (640 × 360, quality 55) rather than a full-resolution desktop PNG.

Those mechanisms are not a guarantee that every request succeeds. Most importantly, Brahma Echo's screen-analysis route uses its own Gemini Live vision session; it does **not** fail over to OpenRouter when that screen request fails. Its queue can also report a request accepted before the asynchronous send or model response has succeeded. “Works every time” is therefore an observation, not a property established by this repository or its tests.

## What routes to which provider?

| Operation | Source behavior | What happens on failure |
|---|---|---|
| Ordinary live conversation | When a Gemini Live session is available, user text is sent into that session. The live model is `models/gemini-2.5-flash-native-audio-preview-12-2025`. | The main session loop reconnects after an error, waiting five seconds between connection attempts. A detected Gemini quota/limit error switches later text requests to the OpenRouter-first fallback path. |
| Direct text fallback | `_fallback_reply` calls Google Gemini `gemini-2.5-flash` first unless the OpenRouter-first flag is already set. The helper contains one `generate_content` call and no application-level retry loop. | An empty Gemini result or exception leads to OpenRouter. A detected Gemini-limit error sets OpenRouter-first for subsequent fallback replies. If both paths fail or return empty text, the user may see the generic “I’m ready, sir.” response rather than a surfaced provider failure. |
| Screen question | The main input handler diverts screen requests to `actions/screen_processor.py`, which sends the image and prompt to a separate Gemini Live vision session. | That session reconnects every two seconds after disconnects, but this route has no OpenRouter fallback. If the session is offline when `screen_process` checks readiness, it returns a failure. After the image is queued, a send error is logged but the image is not resubmitted. |
| General LLM-client calls | `llm_client.py` sends calls to the local OpenAI-compatible service only when the configured provider is exactly `Local`; otherwise it delegates to OpenRouter. Gemini is called separately from `main.py`. | This is not a single universal Gemini/OpenRouter router. The UI also stores an “Automatically switch if a provider fails” setting, but in the reviewed source that setting is only read, displayed, and saved by `ui.py`; the runtime clients do not read it. |

The README describes Gemini plus OpenRouter as providing “resilient fallback support.” That is a useful summary of some text flows, but it should not be read as a guarantee or as a description of every screen/vision flow.

## OpenRouter retries, pool failover, and limits

`or_client.py` has **22 hard-coded text-model IDs** and **8 hard-coded vision-model IDs**. Calls go to OpenRouter’s chat-completions endpoint. With no explicit preferred model, the client walks the relevant pool and returns the first non-empty result. If an explicit model is supplied and fails, the client then walks the pool; when that same ID is also in the pool, it may be attempted again there.

For each model it:

- allows up to **two HTTP attempts**;
- uses a **60-second per-request timeout** and waits **two seconds** before the second attempt;
- marks HTTP **429** models as rate-limited for **60 seconds**, then continues to other models;
- retries other unsuccessful statuses, timeouts, and caught exceptions before moving to the next model;
- raises an all-models-failed error if no model returns content.

This is much more than a single retry. A complete text-pool pass can issue up to **44 model requests** (22 models × 2 attempts); a vision-pool pass can issue up to **16**. These are theoretical per-call maxima, not normal request counts. Calls are serial and there is no overall pool deadline, so a long run of slow timeouts can make a “fallback” take a long time. The 60-second rate-limit cooldown is in memory for the running process, not a persistent account-wide limit manager.

**Source-level authentication-handling caveat:** the client raises `PermissionError` for HTTP 401/403 inside the request `try` block, but its following broad `except Exception` catches that exception. As written, an HTTP 401/403 can therefore be treated as an ordinary failed attempt, retried on that model, and followed by further pool requests; the higher-level `except PermissionError` does not see that swallowed exception. A missing key is checked before that request loop and does fail immediately. This path deserves a focused test/fix before copying the client.

The pool is a fixed list, not a live availability or capability check. OpenRouter can change access, rate limits, model availability, or account terms; IDs ending in `:free` do not promise permanent availability, a particular quota, or that every account will always be able to use them. Brahma Echo can still exhaust or lose access to every candidate.

## Why its screen requests can feel lighter

The UI’s screen-capture helper scales the **primary display** to fit within 640 × 360 and saves JPEG at quality 55. The screen processor’s own capture fallback also downsizes and compresses its image when Pillow is available. That keeps image payloads much smaller and can reduce upload time or image-size failures, at the cost of fine text and detail. The fallback capture implementation can capture all displays, but the normal UI-provided screenshot path is the primary-screen capture.

The screen processor maintains a persistent Gemini Live connection, queues the JPEG and prompt, and handles audio/transcript output. However, `screen_process` returns success once the payload has been queued—not once Gemini has answered. If the send loop finds the session unavailable, it discards the item; if the send call raises, it logs the error without resending the screenshot or switching to OpenRouter. The two-second reconnect loop may restore service for a later request, but it does not make the current request guaranteed.

## Comparison with Otterary

| | Brahma Echo (reviewed snapshot) | Otterary 1.0.1 in this repository |
|---|---|---|
| Screenshot payload | Normally a primary-display JPEG limited to 640 × 360 at quality 55. | Full virtual-desktop PNG, including connected monitors. |
| Gemini route | Gemini Live sessions for live conversation and screen analysis; a separate `gemini-2.5-flash` call in the text fallback. | One direct Gemini request to the user-selected model for a capture. |
| OpenRouter route | Text/vision model pools with per-model attempts and pool failover in the shared OpenRouter client. | One request to the configured OpenRouter vision model; no model-pool or provider fallback. |
| Retry policy | Session reconnect loops plus repeated OpenRouter requests. | Exactly one provider HTTP attempt per accepted capture. |

Otterary’s shared Gemini/OpenRouter helper functions still have retry-capable defaults for other app families, but the Otterary call sites explicitly pass `retry_transient_errors=False`. Its regression tests cover that no-retry behavior. Copying Brahma Echo’s retries, OpenRouter model pool, or Gemini-to-OpenRouter fallback would change Otterary’s current one-attempt contract; **no Otterary behavior was changed for this analysis**.

A smaller JPEG could be evaluated independently as a payload/performance change, but it can make small screen text harder to read. That should be treated as a separate product decision, not as a reliability guarantee. An exact Brahma-style port would require explicitly revisiting the no-retry requirement first.

## Reliability verdict

Brahma Echo’s apparent advantage is plausibly explained by a combination of persistent Gemini Live sessions, reconnect loops, smaller screen images, and OpenRouter’s model diversity and repeated attempts on fallback paths. But those advantages apply to different routes, with trade-offs in latency, request volume, model consistency, and image detail. A screen question is not automatically retried through OpenRouter, and an OpenRouter pool can still fail, run slowly, or behave unexpectedly on authentication errors.

The reviewed repository contains screen-processor unit tests with mocked capture/session behavior, but no dedicated `test_or_client.py` or `test_llm_client.py` covering live provider failover, model-pool retry limits, authentication errors, or end-to-end reliability. The code supports the conclusion that Brahma Echo makes more recovery attempts in some paths; it does **not** prove that it “works every time.”

## Source references

- [README: Gemini + OpenRouter fallback claims](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/README.md#L38-L56)
- [Main routing and direct Gemini text fallback](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/main.py#L289-L303), [user-input routing](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/main.py#L2490-L2541), and [fallback reply](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/main.py#L3358-L3404)
- [Main Gemini Live reconnect loop](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/main.py#L4307-L4404)
- [OpenRouter model lists and request/retry logic](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/or_client.py#L36-L80) and [fallback pool](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/or_client.py#L109-L237)
- [Generic provider routing](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/llm_client.py#L20-L78)
- [Screen image sizing, Gemini Live reconnection, send queue, and result handling](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/actions/screen_processor.py#L35-L52), [image compression](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/actions/screen_processor.py#L110-L145), [live connection and send loop](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/actions/screen_processor.py#L200-L269), and [screen request dispatch](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/actions/screen_processor.py#L360-L455)
- [UI screenshot capture](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/ui.py#L9555-L9579) and [provider-switch setting](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/ui.py#L10760-L10761)
- [Screen-processor tests](https://github.com/titechprabhasolutions/Brahma-Echo/blob/2439ebf5df27e10420962fa091ecb75677dfdca9/tests/test_screen_processor.py#L7-L65)
- This repository’s [Otterary request call sites](../answer_tray.py#L5488-L5505) and [no-retry documentation](otterary.md#request-behavior).
