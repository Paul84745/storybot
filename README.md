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
- **Gameplay (preferred):** record your own gameplay (e.g. Fortnite parkour), then on GitHub
  go to Releases → new release with tag `backgrounds` and attach the `.mp4` files.
  Every video picks a random clip and a random start point. If a filename contains
  "fortnite", Epic's required disclaimer is added to the caption automatically.
- **AI scenes (default until clips exist):** 6 AI illustrations per part with slow zoom.
- Force one mode with a repo variable `BG_MODE` = `gameplay`, `scenes` or `gradient`.

## Voice
Microsoft neural voices (Ava, Emma, Andrew, Brian…) with exact word timing for captions;
an offline voice is used automatically if that service is down.

## Posting
Post Part 1 in the morning, Part 2 at midday, Part 3 in the evening.
Turn on TikTok's "AI-generated content" label when posting.
