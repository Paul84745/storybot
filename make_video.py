"""Render a multi-part TikTok story series from a story JSON file.

Story JSON:
{
  "title": "hook title",
  "narrator": "female" | "male",
  "voice": "af_heart",                  # Kokoro fallback voice
  "parts": ["part 1 text", "part 2 text", "part 3 text"],
  "scenes": [["image prompt", ...], ...] # optional, one list per part
}

Voice: Microsoft neural voices via edge-tts (natural, exact word timing);
falls back to the offline Kokoro voice if that service is unreachable.

Background, in order of preference (override with BG_MODE=gameplay|scenes|gradient):
  1. gameplay  – random clip from backgrounds/*.mp4 (your own recorded gameplay)
  2. scenes    – AI illustrations of the story with slow zoom/pan
  3. gradient  – animated colour gradient
"""
import asyncio, glob, time, json, os, random, re, subprocess, sys, urllib.parse, urllib.request
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
MIN_SECONDS = float(os.environ.get("MIN_SECONDS", 62))
EDGE_VOICES = {   # picked by Paul from the voice sampler (#3 Ava, #1 Andrew)
    "female": ["en-US-AvaMultilingualNeural"],
    "male": ["en-US-AndrewMultilingualNeural"],
}
PALETTES = [
    ("0x1a0b2e", "0x6a1b9a", "0xff4081", "0x0d47a1"),
    ("0x04121f", "0x00838f", "0x26c6da", "0x283593"),
    ("0x1b0000", "0xb71c1c", "0xff6f00", "0x4a148c"),
]


def run(cmd):
    subprocess.run(cmd, check=True)


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------- voice: edge-tts
async def _edge(text, voice, rate, mp3):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append([ch["text"], s, s + ch["duration"] / 1e7])
    return words


def edge_narrate(text, voice, rate, base):
    mp3 = base + ".mp3"
    raw = asyncio.run(_edge(text, voice, rate, mp3))
    if not raw:
        raise RuntimeError("no word timings")
    # re-attach punctuation from the source text so captions break naturally
    toks = text.split()
    ti = 0
    for w in raw:
        key = re.sub(r"\W", "", w[0]).lower()
        for j in range(ti, min(ti + 4, len(toks))):
            if re.sub(r"\W", "", toks[j]).lower().startswith(key[:3]):
                if re.search(r"[.,!?;:…]$", toks[j]):
                    w[0] = w[0] + toks[j][-1] if not re.search(r"[.,!?;:…]$", w[0]) else w[0]
                ti = j + 1
                break
    return mp3, [tuple(w) for w in raw]


# ---------------------------------------------------------------- voice: kokoro fallback
_kokoro = None
def kokoro_narrate(text, voice, speed, base):
    global _kokoro
    from kokoro_onnx import Kokoro
    if _kokoro is None:
        _kokoro = Kokoro(os.path.join(HERE, "models/kokoro.onnx"), os.path.join(HERE, "models/voices.bin"))
    sents = [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s]
    groups, cur = [], ""
    for s in sents:  # 1-2 sentence groups keep intonation natural
        if cur and len(cur) + len(s) > 200:
            groups.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur: groups.append(cur)
    sr, chunks, words, t = 24000, [], [], 0.0
    for g in groups:
        a, sr = _kokoro.create(g, voice=voice, speed=speed, lang="en-us")
        nz = np.where(np.abs(a) > 0.008)[0]
        if len(nz):
            a = a[max(nz[0] - 800, 0): nz[-1] + 2400]
        dur = len(a) / sr
        toks = g.split()
        wts = [max(1, len(re.findall(r"[aeiouy]+", w.lower()))) + 0.6 + (0.8 if re.search(r"[.,!?]$", w) else 0) for w in toks]
        pos = t
        for w, wt in zip(toks, wts):
            d = dur * wt / sum(wts); words.append((w, pos, pos + d)); pos += d
        pause = np.zeros(int(sr * random.uniform(0.22, 0.34)), dtype=np.float32)
        chunks += [a.astype(np.float32), pause]
        t += dur + len(pause) / sr
    wav = base + ".wav"
    sf.write(wav, np.concatenate(chunks), sr)
    return wav, words


def narrate(text, story, base):
    """Returns (audio_path, words, duration), slowing down if under a minute."""
    gender = story.get("narrator", "female")
    voice = os.environ.get("VOICE") or story.get("edge_voice") or random.Random(story.get("title")).choice(EDGE_VOICES[gender])
    try:
        rate = int(os.environ.get("VOICE_RATE", 10))  # brisk, energetic delivery
        for _ in range(3):
            audio, words = edge_narrate(text, voice, f"{rate:+d}%", base)
            dur = probe_duration(audio)
            if dur >= MIN_SECONDS or rate <= 0:
                break
            rate = max(0, int(rate - (MIN_SECONDS + 1.5 - dur) / dur * 100) - 1)
        print(f"::notice::voice {voice} ({rate:+d}%), {dur:.0f}s")
    except Exception as e:
        print(f"::warning::natural voice unavailable ({e}); using offline voice")
        speed = 1.0
        audio, words = kokoro_narrate(text, story.get("voice", "af_heart"), speed, base)
        dur = probe_duration(audio)
        if dur < MIN_SECONDS:
            speed = max(0.86, speed * dur / (MIN_SECONDS + 1))
            audio, words = kokoro_narrate(text, story.get("voice", "af_heart"), speed, base)
            dur = probe_duration(audio)
    return audio, words, max(dur, MIN_SECONDS + 0.3) + 0.6


# ---------------------------------------------------------------- captions
def ass_time(x):
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def esc(w):
    return w.replace("{", "(").replace("}", ")")


def build_ass(words, total, part_label, title, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Poppins,112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,8,3,5,80,80,0,1
Style: Badge,Poppins,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,3,14,0,8,0,0,170,1
Style: Label,Poppins,36,&H00E6E6E6,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,0,8,0,0,265,1
Style: Title,Poppins,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,2,8,90,90,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 1,{ass_time(0)},{ass_time(total)},Badge,,0,0,0,,{part_label}"]
    if title:
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(4.5)},Title,,0,0,0,,{{\\fad(0,400)}}{esc(title)}")
    groups, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        if len(cur) == 2 or re.search(r"[.,!?;:…]$", w[0]) or (nxt and nxt[1] - w[2] > 0.25):
            groups.append(cur); cur = []
    if cur: groups.append(cur)
    for gi, g in enumerate(groups):
        nxt_start = groups[gi + 1][0][1] if gi + 1 < len(groups) else g[-1][2] + 0.4
        for i, (w, s, e) in enumerate(g):
            end = g[i + 1][1] if i + 1 < len(g) else min(nxt_start, e + 0.35)
            hl = "{\\c&H00E5FF&}" if gi % 3 else "{\\c&H66FF33&}"   # alternate highlight colours
            txt = " ".join((hl + esc(x) + "{\\c&HFFFFFF&}") if j == i else esc(x)
                           for j, (x, _, _) in enumerate(g))
            pop = "\\fscx72\\fscy72\\t(0,90,\\fscx106\\fscy106)\\t(90,150,\\fscx100\\fscy100)" if i == 0 else ""
            ev.append(f"Dialogue: 0,{ass_time(s)},{ass_time(max(end, s + 0.05))},Cap,,0,0,0,,{{\\pos({W//2},{H//2 - 230}){pop}}}{txt}")
    with open(path, "w") as f:
        f.write(head + "\n".join(ev) + "\n")


# ---------------------------------------------------------------- backgrounds
def fetch_image(prompt, seed, path):
    style = ", cinematic photo, bright natural light, vertical composition, highly detailed, no text"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:300] + style) +
           f"?width={W}&height={H}&nologo=true&seed={seed}&model=flux")
    for attempt in range(4):
        time.sleep(46 if attempt == 0 else 20 * attempt)  # free tier: one image per 45s per IP
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 storybot"})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = r.read()
            if len(data) > 20000 and (data[:2] == b"\xff\xd8" or data[:4] == b"\x89PNG"):
                open(path, "wb").write(data)
                return True
            print(f"::warning::image: unexpected reply ({len(data)} bytes)")
        except Exception as e:
            body = e.read().decode(errors="ignore")[:150] if hasattr(e, "read") else ""
            print(f"::warning::image attempt {attempt + 1} failed: {e} {body}")
    return False


def scenes_background(prompts, total, base):
    imgs = []
    for i, p in enumerate(prompts):
        path = f"{base}_s{i}.jpg"
        if fetch_image(p, random.randint(1, 10**6), path):
            imgs.append(path)
    print(f"::notice::{len(imgs)}/{len(prompts)} scene images generated")
    if len(imgs) < 2:
        return None
    seg = total / len(imgs)
    frames = int(seg * FPS) + 2
    inputs, filters = [], []
    for i, img in enumerate(imgs):
        inputs += ["-loop", "1", "-t", f"{seg + 0.1:.2f}", "-i", img]
        zin = i % 2 == 0  # alternate zoom-in / zoom-out
        z = "min(1+0.0009*on,1.18)" if zin else "max(1.18-0.0009*on,1)"
        filters.append(f"[{i}:v]scale={int(W*1.2)}:{int(H*1.2)}:force_original_aspect_ratio=increase,"
                       f"crop={int(W*1.2)}:{int(H*1.2)},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                       f":d={frames}:s={W}x{H}:fps={FPS},trim=duration={seg:.2f},setpts=PTS-STARTPTS[s{i}]")
    filters.append("".join(f"[s{i}]" for i in range(len(imgs))) + f"concat=n={len(imgs)}:v=1:a=0[v]")
    out = base + "_bg.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out])
    for img in imgs:
        os.remove(img)
    return out


def background_input(mode, prompts, total, base, idx):
    """gameplay (default): your own clips if uploaded, else generated 3D parkour run."""
    clips = sorted(glob.glob(os.path.join(HERE, "backgrounds", "*.mp4")))
    if mode in ("auto", "gameplay"):
        if clips:
            clip = random.choice(clips)
            start = random.uniform(0, max(0, probe_duration(clip) - total - 1))
            return (["-ss", f"{start:.1f}", "-stream_loop", "-1", "-i", clip],
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=brightness=-0.06", clip)
        try:
            import gameplay
            bg = gameplay.render(base + "_bg.mp4", total + 0.5)
            print("::notice::generated 3D parkour gameplay background")
            return ["-i", bg], "eq=saturation=1.08", bg
        except Exception as e:
            print(f"::warning::gameplay renderer failed ({e!r}); falling back")
    if mode in ("auto", "gameplay", "scenes") and prompts:
        bg = scenes_background(prompts, total, base)
        if bg:
            return ["-i", bg], "eq=brightness=-0.03:saturation=1.1", bg
    c = random.choice(PALETTES)
    return (["-f", "lavfi", "-i", f"gradients=s=270x480:r={FPS}:n=4:speed=0.015:type=radial:"
             f"c0={c[0]}:c1={c[1]}:c2={c[2]}:c3={c[3]}:seed={idx * 7}"],
            f"scale={W}:{H}:flags=bicubic,gblur=sigma=8,noise=alls=6:allf=t", None)


# ---------------------------------------------------------------- main
def render_part(story, idx, out_dir):
    n = len(story["parts"])
    text = story["parts"][idx - 1].rstrip()
    text += f" Follow for part {idx + 1}." if idx < n else " Follow for more stories."
    if idx > 1:
        text = f"Part {idx}. " + text
    base = os.path.join(out_dir, f"part{idx}")
    audio, words, total = narrate(text, story, base)
    build_ass(words, total, f"PART {idx}/{n}", story.get("title", ""), base + ".ass")
    scenes = (story.get("scenes") or [[]] * n)[idx - 1] if story.get("scenes") else []
    bg_in, bg_vf, bg_file = background_input(os.environ.get("BG_MODE", "auto"), scenes, total, base, idx)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *bg_in, "-i", audio,
         "-filter_complex", f"[0:v]{bg_vf},ass={base}.ass[v];[1:a]apad,loudnorm=I=-14:TP=-1.5[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", base + ".mp4"])
    for f in (audio, base + ".mp3", base + ".ass", base + "_bg.mp4"):
        if os.path.exists(f):
            os.remove(f)
    return base + ".mp4", total, bg_file


def main(story_path, out_dir):
    story = json.load(open(story_path))
    os.makedirs(out_dir, exist_ok=True)
    used = []
    for i in range(1, len(story["parts"]) + 1):
        path, dur, bg = render_part(story, i, out_dir)
        used.append(os.path.basename(bg) if bg else "")
        print(f"{path}  {dur:.1f}s")
    json.dump({"backgrounds": used}, open(os.path.join(out_dir, "meta.json"), "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out")
