"""Ask Gemini for a new 3-part fictional story and save it as story JSON.

Usage: python write_story.py stories/<name>.json
Needs GEMINI_API_KEY or GROQ_API_KEY. Keeps a history of past titles in state/history.json
so stories don't repeat.
"""
import json, os, random, re, sys, urllib.request
from datetime import date

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
HIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "history.json")

GENRES = [
    "family betrayal and a satisfying, legal revenge",
    "workplace drama where a smug boss or coworker gets exposed",
    "entitled neighbor conflict with a clever, petty-but-legal payback",
    "wedding or relationship drama with a twist reveal",
    "inheritance or money dispute where the quiet person wins",
    "roommate or landlord drama with an unexpected turn",
]
VOICES = ["af_heart", "af_bella", "af_nicole", "am_michael", "am_adam", "bf_emma"]

PROMPT = """Write an original, fictional first-person story for a 3-part TikTok narration series.
Genre: {genre}.
Rules:
- Exactly 3 parts. Each part 240 to 270 words of plain spoken prose (no headings, no emojis, no lists).
- Part 1 opens with a one-sentence hook that creates instant curiosity.
- Parts 1 and 2 end on a cliffhanger. Part 3 resolves it with a satisfying payoff.
- Revenge must stay legal and non-violent. No real people, brands or places. No sexual content, slurs or gore.
- Simple words, short punchy sentences, written to be read aloud with energy. Spell out numbers.
- Keep tension high the whole time: a new reveal, twist or escalation every few sentences; no slow backstory.
- Use direct dialogue lines and vivid reactions. Part 2 and 3 open by instantly reminding the viewer what is at stake.
- Do not write "follow for part 2"; that is added automatically.
- Avoid these previously used titles/premises: {avoid}
Also write:
- a title (max 9 words, the hook, no quotes)
- a TikTok caption (max 140 chars, ends with 3-5 relevant hashtags including #storytime)
- narrator: "female" or "male", matching the first-person narrator
- scenes: for EACH part, 6 image prompts that illustrate that part in order (one visual moment each,
  max 25 words, describe people by appearance only, keep each character's look identical in every prompt,
  no names, no text or signs in the image, nothing graphic)
Return ONLY JSON: {{"title": "...", "caption": "...", "narrator": "female", "parts": ["...", "...", "..."], "scenes": [["..."], ["..."], ["..."]]}}"""


def gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, json.dumps(body).encode(), {
        "Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"]


GROQ_PREFERRED = [m for m in [os.environ.get("GROQ_MODEL")] if m] + [
    "openai/gpt-oss-120b", "openai/gpt-oss-20b"]


def groq_call(path, body=None):
    req = urllib.request.Request("https://api.groq.com/openai/v1/" + path,
                                 json.dumps(body).encode() if body else None, {
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
        "User-Agent": "storybot"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def groq_models():
    """Preferred models first, then whatever large chat models Groq currently offers."""
    try:
        live = [m["id"] for m in groq_call("models")["data"]]
    except Exception:
        return GROQ_PREFERRED
    extra = [m for m in live if m not in GROQ_PREFERRED and not re.search(r"whisper|tts|guard|orpheus|playai|compound", m)]
    extra.sort(key=lambda m: -max([int(x) for x in re.findall(r"(\d+)b", m)] or [0]))
    return [m for m in GROQ_PREFERRED if m in live] + extra


def groq(prompt):
    last = None
    for model in groq_models():
        body = {"model": model, "temperature": 1.0, "max_completion_tokens": 8000,
                "messages": [{"role": "user", "content": prompt}]}
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"
        try:
            text = groq_call("chat/completions", body)["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                return m.group(0)
            print(f"::warning::groq {model} returned no JSON")
        except Exception as e:
            last = e
            detail = e.read().decode()[:300] if hasattr(e, "read") else ""
            print(f"::warning::groq {model} failed: {e} {detail}")
    raise last or RuntimeError("no Groq model returned a story")


def write(prompt):
    """Use Gemini if a key is set, otherwise (or if it fails) Groq."""
    if os.environ.get("GEMINI_API_KEY"):
        try:
            return gemini(prompt)
        except Exception as e:
            print(f"::warning::gemini failed: {e}")
            if not os.environ.get("GROQ_API_KEY"):
                raise
    return groq(prompt)


def valid(s):
    return (isinstance(s, dict) and s.get("title") and len(s.get("parts", [])) == 3
            and all(200 <= len(p.split()) <= 310 for p in s["parts"]))


def main(out):
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        sys.exit("::error::No GROQ_API_KEY or GEMINI_API_KEY secret found in the repo")
    hist = json.load(open(HIST)) if os.path.exists(HIST) else []
    avoid = "; ".join(h["title"] for h in hist[-40:]) or "none"
    for attempt in range(4):
        raw = write(PROMPT.format(genre=random.choice(GENRES), avoid=avoid))
        raw = re.sub(r"^```(json)?|```$", "", raw.strip())
        try:
            story = json.loads(raw)
        except json.JSONDecodeError:
            print(f"::warning::attempt {attempt + 1}: reply was not JSON: {raw[:150]!r}")
            continue
        if valid(story):
            break
        lens = [len(p.split()) for p in story.get("parts", [])] if isinstance(story, dict) else []
        print(f"::warning::attempt {attempt + 1}: story rejected (part word counts {lens})")
    else:
        sys.exit("::error::The AI did not return a usable story")
    story["voice"] = random.choice(VOICES)
    if story.get("narrator") not in ("female", "male"):
        story["narrator"] = "female"
    sc = story.get("scenes")
    if not (isinstance(sc, list) and len(sc) == 3 and all(isinstance(x, list) and x for x in sc)):
        story.pop("scenes", None)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(story, open(out, "w"), indent=2)
    hist.append({"date": date.today().isoformat(), "title": story["title"]})
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    json.dump(hist, open(HIST, "w"), indent=2)
    print(story["title"])


if __name__ == "__main__":
    main(sys.argv[1])
