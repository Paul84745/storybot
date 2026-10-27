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
FORCE_TYPE = os.environ.get("FORCE_TYPE", "").strip()
VOICES = ["af_heart", "af_bella", "af_nicole", "am_michael", "am_adam", "bf_emma"]


def playbook():
    try:
        return open(os.path.join(HERE, "playbook.md")).read()
    except OSError:
        return ""


BRAINSTORM = """You are the head writer of a hugely successful TikTok storytime account (original fiction,
narrated over gameplay). Follow this playbook:

{playbook}

Recent stories (do NOT repeat their premise; do NOT use these recent story types: {last_type}):
{avoid}

{only}
For each give: type, hook (the one shocking first sentence the narrator says), twist (the reveal the
viewer won't see coming), debate (why viewers will argue in the comments), and score 1-100 for how
likely it is to go viral and keep viewers on the edge of their seat (be harsh: anything without real danger,
a ticking clock or a gripping mystery scores under 60; generic or predictable ideas score under 50).
Return ONLY JSON: {{"premises": [{{"type": "...", "hook": "...", "twist": "...", "debate": "...", "score": 0}}]}}"""

WRITE = """You are the head writer of a hugely successful TikTok storytime account. Follow this playbook:

{playbook}

Write this premise as an original, fictional story for a 3-part narrated series (first person; for a "What if"
scenario use third person with a named main character):
Type: {type}
Opening hook: {hook}
Twist: {twist}
Debate angle: {debate}

Rules:
- Exactly 3 parts, each 220 to 250 words of spoken prose (no headings, emojis or lists).
- Part 1's FIRST sentence is the hook (you may sharpen it). No preamble.
- Parts 1 and 2 stop right before a major revelation. Parts 2 and 3 open with a one-line recap of the stakes.
- Part 3 pays everything off with the twist and ends by asking the viewer for their verdict.
- Edge-of-your-seat suspense: present tense, a ticking clock, rising danger, false relief, sensory details at peak moments.
- Simple words, short punchy sentences, dialogue, written to be read aloud with energy. Spell out numbers.
- Do not write "follow for part 2" (added automatically). No real people, brands or places.
- On-screen stamps: put 3 to 6 chapter stamps per part INLINE in the text as [[LABEL]], right before the
  sentence they introduce. Labels are short ALL CAPS, max 24 characters: time/place, a rule or a countdown,
  e.g. [[DAY 1 · 06:40]], [[RULE 2 · DISGUISE]], [[9:41 PM · KITCHEN]], [[3 MINUTES LEFT]]. Part 1 starts with one.
Also write:
- title: the hook in max 9 words (can be a question), no quotes
- captions: 3 TikTok captions (one per part, max 150 chars each, each ending with 6-8 hashtags mixing
  #storytime #fyp #foryou #drama with topic tags; part 3's caption asks viewers for their verdict)
- narrator: "female" or "male" (the narrating voice; for third person pick what fits the story)
- scenes: for EACH part, 8 short visual descriptions that illustrate it in order, for flat cartoon illustrations
  (one simple moment each, max 20 words, describe characters by appearance and keep them identical, no text, nothing graphic)
Return ONLY JSON: {{"title": "...", "type": "{type}", "narrator": "female", "captions": ["...", "...", "..."], "parts": ["...", "...", "..."], "scenes": [["..."], ["..."], ["..."]]}}"""

EDIT = """You are a ruthless TikTok retention editor. Viewers swipe away the instant a story gets slow.
Playbook:

{playbook}

This is Part {n} of 3 of the story "{title}". Rewrite it so viewers watch every second:
{goal}
- Cut backstory, filler and explaining feelings; replace them with escalation, dialogue and reveals.
- Crank up the suspense: present tense, ticking clock, sensory details, very short sentences at the scariest moments.
- Keep the same events, narrator and facts. About {words} words (never shorter, at most 10% longer).
- Keep every [[STAMP]] marker exactly as written, in front of the same moment.

Part {n}:
{text}

Return ONLY JSON: {{"text": "the rewritten part"}}"""

GOALS = {
    1: "- Make the first sentence as shocking and specific as possible.\n- End right before a revelation so the viewer NEEDS Part 2.",
    2: "- Open with a one-line recap of the stakes.\n- End right before an even bigger revelation so the viewer NEEDS Part 3.",
    3: "- Open with a one-line recap of the stakes.\n- Make the payoff as satisfying as possible and end by asking the viewer for their verdict.",
}


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


def nwords(text):
    return len(re.sub(r"\[\[.*?\]\]", " ", text).split())


def valid(s):
    return (isinstance(s, dict) and s.get("title") and isinstance(s.get("parts"), list) and len(s["parts"]) == 3
            and all(isinstance(p, str) and 180 <= nwords(p) <= 360 for p in s["parts"]))


WHATIF_BRAIN = """
Each premise is a world-changing "What if...?" that hits everyone at once, with ONE named person caught in it:
e.g. what if every man vanished overnight except one; what if your phone showed how many days everyone has left;
what if the sun didn't rise and only one girl could still see in the dark; what if every lie you told appeared
on your forehead. The hook is the "What if...?" question itself. NOT a personal mystery or a crime story."""

WHATIF_WRITE = """
This is a "What if" scenario. Follow this structure exactly:
- Third person, present tense, a named main character. Part 1's first sentence is the "What if...?" question.
- Part 1: the world-changing event on DAY 1, what it means, and the first survival rules (RULE 1, RULE 2), each with a
  vivid reason. End as a threat appears (a drone, a voice, a knock, a tracker).
- Part 2: time jumps (DAY 2, DAY 3...), RULE 3 and RULE 4, a hideout, the threat closing in, a voice or message that
  claims to want to help. End mid-action.
- Part 3: DAY 7 or later, the confrontation or escape, and a twist that reveals a bigger world (a note, a message,
  a location, "you are not the only one"). End on that mystery and ask viewers what they would do.
- At least 4 [[STAMP]] markers in EVERY part: every time jump and every rule gets its own stamp."""


def is_whatif(t):
    return "what if" in str(t).lower()


def stamps_ok(story, need):
    return all(p.count("[[") >= need for p in story["parts"])


def pick_premise(hist):
    recent = hist[-30:]
    avoid = "\n".join(f"- [{h.get('type', '?')}] {h['title']}" for h in recent) or "- none yet"
    recent_types = [str(h.get("type", "")).lower() for h in recent[-3:]]
    last_type = ", ".join(t for t in recent_types if t) or "none"
    for attempt in range(3):
        only = (f"Brainstorm 10 fresh, original premises, ALL of this story type: {FORCE_TYPE}." + (WHATIF_BRAIN if is_whatif(FORCE_TYPE) else "")
                if FORCE_TYPE else
                "Brainstorm 10 fresh, original premises spread across at least 6 different story types.")
        data = parse(write(BRAINSTORM.format(playbook=playbook(), avoid=avoid, last_type=last_type, only=only)))
        prem = [p for p in (data or {}).get("premises", []) if isinstance(p, dict) and p.get("hook")]
        if FORCE_TYPE:
            for p in prem:
                p["type"] = FORCE_TYPE
        else:
            prem = [p for p in prem if str(p.get("type", "")).lower() not in recent_types] or prem
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
    need = 4 if is_whatif(prem.get("type")) else 2
    extra = WHATIF_WRITE if is_whatif(prem.get("type")) else ""
    fallback = None
    for attempt in range(5):
        cand = parse(write(WRITE.format(playbook=playbook(), **{k: prem.get(k, "") for k in ("type", "hook", "twist", "debate")}) + extra))
        if valid(cand):
            if stamps_ok(cand, need):
                story = cand
                break
            fallback = fallback or cand
            print(f"::warning::draft {attempt + 1} has too few stamps {[p.count('[[') for p in cand['parts']]}")
            continue
        lens = [nwords(p) for p in cand.get("parts", []) if isinstance(p, str)] if isinstance(cand, dict) else []
        print(f"::warning::draft {attempt + 1} rejected (part word counts {lens})")
    story = story or fallback
    if not story:
        sys.exit("::error::The AI did not return a usable story")
    improved = 0
    for i, part in enumerate(story["parts"]):
        n = nwords(part)
        try:
            res = parse(write(EDIT.format(playbook=playbook(), n=i + 1, title=story["title"], goal=GOALS[i + 1],
                                          words=n, text=part)))
            new = (res or {}).get("text") if isinstance(res, dict) else None
        except Exception as e:
            new = None
            print(f"::warning::editor failed on part {i + 1}: {e}")
        if isinstance(new, str) and 0.92 * n <= nwords(new) <= max(n * 1.12, 270) and new.count("[[") >= part.count("[[") - 1:
            story["parts"][i] = new.strip()
            improved += 1
        else:
            print(f"::warning::editor kept original part {i + 1} ({len(new.split()) if isinstance(new, str) else 0} vs {n} words)")
    print(f"::notice::editor improved {improved}/3 parts")
    story["voice"] = random.choice(VOICES)
    story["premise"] = prem
    if story.get("narrator") not in ("female", "male"):
        story["narrator"] = "female"
    sc = story.get("scenes")
    if not (isinstance(sc, list) and len(sc) == 3 and all(isinstance(x, list) and x for x in sc)):
        story.pop("scenes", None)
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
