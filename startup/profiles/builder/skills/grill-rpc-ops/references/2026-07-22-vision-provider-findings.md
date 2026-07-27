# Vision Model — zai API Findings

**Discovered:** 2026-07-22 during builder config setup

## The Problem

zai API (`api.z.ai`) has **NO vision-capable models**. Tested:

| Model | Vision Support | Evidence |
|-------|---------------|----------|
| glm-4.5 | No | Available on API but text-only |
| glm-4.5-air | No | Available on API but text-only |
| glm-4.6 | No | API returns error: `messages.content.type is invalid, allowed values: ['text']` |
| glm-4.7 | No | Available on API but text-only |
| glm-5 | No | Available on API but text-only |
| glm-5-turbo | No | Available on API but text-only |
| glm-5.1 | No | Available on API but text-only |
| glm-5.2 | No | Available on API but text-only |

**Full model list from zai API** (2026-07-22):
glm-4.5, glm-4.5-air, glm-4.6, glm-4.7, glm-5, glm-5-turbo, glm-5.1, glm-5.2

No model accepts image content types. The `z.ai` endpoint appears to be a coding-only proxy.

## The Config Key

Vision model is configured via `auxiliary.vision`, NOT `model.vision`:

```yaml
auxiliary:
  vision:
    provider: zai      # This won't work — zai has no vision
    model: glm-4.6     # Not actually a vision model
```

The correct key was discovered by reading `hermes_cli/config.py`:
- Line 1149: `configured auxiliary.vision.provider`
- Line 1576: `"auxiliary": {...}` block with vision entry

## Solutions

### Option 1: OpenRouter (requires API key)
Models: `anthropic/claude-sonnet-4`, `openai/gpt-4o`, `google/gemini-pro-vision`

### Option 2: Google Gemini (free tier available)
Model: `gemini-pro-vision` — free tier supports vision

### Option 3: ZhipuAI direct API (GLM-4V)
The original Chinese API likely has GLM-4V — the `z.ai` proxy strips vision

## Current State (2026-07-22)

Builder config has `auxiliary.vision: {provider: zai, model: glm-4.6}` — this will **fail** if a vision call is made. Needs to be updated to a real vision provider before the builder attempts any image analysis.
