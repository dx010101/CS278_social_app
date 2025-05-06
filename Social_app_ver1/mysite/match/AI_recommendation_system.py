import os
import json
import re
import logging
import asyncio
from openai import OpenAI
# instantiate the new client once
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
client = OpenAI(api_key='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')

async def extract_keywords(text: str) -> list[str]:
    prompt = f"""Extract the top 5–10 keywords (single words or short phrases) \
from the following user request.  Return a JSON list of strings, nothing else:

"{text}"
"""
    messages = [
        {"role": "system", "content": "You are a keyword extractor."},
        {"role": "user",   "content": prompt},
    ]

    # Call the API off the event loop
    resp = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.0,
    )

    content = resp.choices[0].message.content.strip()
    logger.info("raw extractor output: %r", content)

    # 1) try strict JSON
    try:
        kws = json.loads(content)
        if isinstance(kws, list):
            return kws
    except Exception:
        logger.warning("JSON parse failed, falling back…")

    # 2) try Python literal eval (sometimes models emit Python lists)
    try:
        kws = eval(content, {}, {})
        if isinstance(kws, list):
            return kws
    except Exception:
        logger.warning("literal eval failed, falling back…")

    # 3) pull out any quoted strings
    quoted = re.findall(r'"([^"]+)"', content)
    if quoted:
        logger.info("using quoted‐string fallback: %r", quoted)
        return quoted

    # 4) final fallback: split on commas or newlines
    parts = re.split(r"[\n,]+", content)
    cleaned = [p.strip(" -–•\t") for p in parts if p.strip()]
    logger.info("using split fallback: %r", cleaned)
    print(cleaned)
    return cleaned