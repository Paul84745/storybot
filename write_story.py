"""Write a new 3-part fictional story series and save it as story JSON.

Three stages, guided by playbook.md (proven patterns from top story accounts):
  1. brainstorm 10 premises across proven story types and score them; pick the strongest new one
  2. write the 3 parts with hook-first, cliffhanger structure
  3. an "editor" pass that tightens the hook, escalation and cliffhangers

Usage: python write_story.py stories/<name>.json
Needs GROQ_API_KEY or GEMINI_API_KEY. Past stories are kept in state/history.json.
"""
import json, os, random, re, sys, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
HIST = os.path.join(HERE, "state", "history.json")
VOICES = ["af_heart", "af_bella", "af_nicole", "am_michael", "am_adam", "bf_emma"]


def playbook():
    try:
        return open(os.path.join(HERE, "playbook.md")).read()
    except OSError:
        return ""


BRAINSTORM = """You are the head writer of a hugely successful TikTok storytime account (original fiction,
narrated over gameplay). Follow this playbook:

{playbook}

Recent stories (do NOT repeat their premise or story type; last type used: {last_type}):
{avoid}

Brainstorm 10 fresh, original premises spread across at least 6 different story types.
For each give: type, hook (the one shocking first sentence the narrator says), twist (the reveal the
viewer won't see coming), debate (why viewers will argue in the comments), and score 1-100 for how
likely it is to go viral (be harsh: generic or predictable ideas score under 50).
Return ONLY JSON: {{"premises": [{{"type": "...", "hook": "...", "twist": "...", "debate": "...", "score": 0}}]}}"""

WRITE = """You are the head writer of a hugely successful TikTok storytime account. Follow this playbook:

{playbook}

Write this premise as an original, fictional, first-person story for a 3-part narrated series:
Type: {type}
Opening hook: {hook}
Twist: {twist}
Debate angle: {debate}

Rules:
- Exactly 3 parts, each 220 to 250 words of spoken prose (no headings, emojis or lists).
- Part 1's FIRST sentence is the hook (you may sharpen it). No preamble.
- Parts 1 and 2 stop right before a major revelation. Parts 2 and 3 open with a one-line recap of the stakes.
- Part 3 pays everything off with the twist and ends by asking the viewer for their verdict.
- Simple words, short punchy sentences, dialogue, written to be read aloud with energy. Spell out numbers.
- Do not write "follow for part 2" (added automatically). No real people, brands or places.
Also write:
- title: the hook in max 9 words (can be a question), no quotes
- captions: 3 TikTok captions (one per part, max 150 chars each, each ending with 6-8 hashtags mixing
  #storytime #fyp #foryou #drama with topic tags; part 3's caption asks viewers for their verdict)
- narrator: "female" or "male"
Return ONLY JSON: {{"title": "...", "type": "{type}", "narrator": "female", "captions": ["...", "...", "..."], "parts": ["...", "...", "..."]}}"""

EDIT = """You are a ruthless TikTok retention editor. Viewers swipe away the instant a story gets slow.
Playbook:

{playbook}

Improve this 3-part story so viewers watch every second and follow for the next part:
- Make the first sentence of Part 1 as shocking and specific as possible.
- Cut any backstory, filler or explaining feelings; replace with escalation, dialogue and reveals.
- Make sure the end of Parts 1 and 2 cuts right before a revelation and makes the viewer NEED the next part.
- Make the Part 3 payoff more satisfying, and end it with a verdict question to the viewer.
- Keep the same plot, narrator, title idea and JSON fields (title, type, narrator, captions, parts). Each part must stay 220 to 250 words — count them.

Story JSON:
{story}

Return ONLY the improved story as JSON with the same fields."""


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
    import time
    last = None
    for model in groq_models():
        body = {"model": model, "temperature": 1.0, "max_completion_tokens": 8000,
                "messages": [{"role": "user", "content": prompt}]}
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"
        for tries in range(4):
            try:
                text = groq_call("chat/completions", body)["choices"][0]["message"]["content"] or ""
                m = re.search(r"\{.*\}", text, re.S)
                if m:
                    return m.group(0)
                print(f"::warning::groq {model} returned no JSON")
                break
            except Exception as e:
                last = e
                detail = e.read().decode()[:400] if hasattr(e, "read") else ""
                if getattr(e, "code", None) == 429 and tries < 3:   # free-tier rate limit: wait it out
                    w = re.search(r"try again in ([0-9.]+)s", detail)
                    time.sleep(float(w.group(1)) + 3 if w else 30)
                    continue
                print(f"::warning::groq {model} failed: {e} {detail[:250]}")
                break
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


def parse(raw):
    raw = re.sub(r"^```(json)?|```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None


def valid(s):
    return (isinstance(s, dict) and s.get("title") and isinstance(s.get("parts"), list) and len(s["parts"]) == 3
            and all(isinstance(p, str) and 180 <= len(p.split()) <= 360 for p in s["parts"]))


def pick_premise(hist):
    recent = hist[-30:]
    avoid = "\n".join(f"- [{h.get('type', '?')}] {h['title']}" for h in recent) or "- none yet"
    last_type = recent[-1].get("type", "none") if recent else "none"
    for attempt in range(3):
        data = parse(write(BRAINSTORM.format(playbook=playbook(), avoid=avoid, last_type=last_type)))
        prem = [p for p in (data or {}).get("premises", []) if isinstance(p, dict) and p.get("hook")]
        prem = [p for p in prem if str(p.get("type", "")).lower() != str(last_type).lower()] or prem
        if prem:
            prem.sort(key=lambda p: -float(p.get("score", 0) or 0))
            best = random.choice(prem[:2])   # a little variety among the top ideas
            print(f"::notice::premise ({best.get('score')}): [{best.get('type')}] {best['hook']}")
            return best
        print(f"::warning::brainstorm attempt {attempt + 1} gave no premises")
    sys.exit("::error::Could not brainstorm premises")


def main(out):
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        sys.exit("::error::No GROQ_API_KEY or GEMINI_API_KEY secret found in the repo")
    hist = json.load(open(HIST)) if os.path.exists(HIST) else []
    prem = pick_premise(hist)
    story = None
    for attempt in range(4):
        cand = parse(write(WRITE.format(playbook=playbook(), **{k: prem.get(k, "") for k in ("type", "hook", "twist", "debate")})))
        if valid(cand):
            story = cand
            break
        lens = [len(p.split()) for p in cand.get("parts", []) if isinstance(p, str)] if isinstance(cand, dict) else []
        print(f"::warning::draft {attempt + 1} rejected (part word counts {lens})")
    if not story:
        sys.exit("::error::The AI did not return a usable story")
    edited = parse(write(EDIT.format(playbook=playbook(), story=json.dumps(story, indent=1))))
    if valid(edited):
        for k in ("title", "type", "narrator", "captions"):
            edited.setdefault(k, story.get(k))
        story = edited
        print("::notice::editor pass applied")
    else:
        lens = [len(p.split()) for p in (edited or {}).get("parts", []) if isinstance(p, str)] if isinstance(edited, dict) else "no JSON"
        print(f"::warning::editor pass rejected ({lens}); using first draft")
    story["voice"] = random.choice(VOICES)
    story["premise"] = prem
    if story.get("narrator") not in ("female", "male"):
        story["narrator"] = "female"
    caps = story.get("captions")
    if not (isinstance(caps, list) and len(caps) == 3 and all(isinstance(c, str) for c in caps)):
        story["captions"] = [f"{story['title']} (part {i}) #storytime #fyp #foryou #drama" for i in (1, 2, 3)]
    story["caption"] = story["captions"][0]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(story, open(out, "w"), indent=2)
    hist.append({"date": date.today().isoformat(), "title": story["title"], "type": story.get("type", prem.get("type"))})
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    json.dump(hist, open(HIST, "w"), indent=2)
    print(story["title"])


if __name__ == "__main__":
    main(sys.argv[1])
