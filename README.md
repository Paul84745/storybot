# storybot

Daily AI story series for TikTok, fully automated on GitHub Actions (free).

Every day it:
1. Writes a new original 3-part fictional story with Gemini or Groq (no repeats — see `state/history.json`)
2. Narrates it with a natural AI voice, free
3. Renders 3 vertical videos, each just over 1 minute, with word-by-word captions,
   a hook title, a "PART X/3" badge and an "AI-generated fictional story" label
4. Publishes them as a GitHub Release with ready-to-paste captions

## Setup (once)
- Repo secret `GROQ_API_KEY` and/or `GEMINI_API_KEY` (Gemini is tried first, Groq as backup)
- Actions → storybot → Run workflow to test

## Backgrounds
- **Generated 3D parkour gameplay (default):** a character runs and jumps across floating block
  platforms, collecting gems, with a fresh course and colour theme every video. Fully original footage.
- **Your own gameplay:** upload `.mp4` clips to a release tagged `backgrounds` and they're used instead
  (random clip, random start). Filenames containing "fortnite" get Epic's disclaimer in the caption.
- Repo variable `BG_MODE` = `gameplay` (default), `scenes` (AI illustrations) or `gradient`.

## Voice
Ava (female narrators) and Andrew (male narrators), Microsoft neural voices, at a brisk +10% pace (repo variable `VOICE_RATE`),
with exact word timing for the pop-in captions;
an offline voice is used automatically if that service is down.

## Posting
Post Part 1 in the morning, Part 2 at midday, Part 3 in the evening.
Turn on TikTok's "AI-generated content" label when posting.
