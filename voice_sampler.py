"""Render one video where the same hook is read by many candidate voices, numbered on screen.

Usage: python voice_sampler.py out.mp4
Pick a number, then set the repo variable VOICE (e.g. en-GB-RyanNeural) to lock it in.
"""
import asyncio, subprocess, sys, os
import edge_tts

LINE = ("My sister booked my wedding venue for herself. Same date. Same flowers. "
        "And she had no idea I already knew.")
VOICES = [
    ("en-US-AndrewMultilingualNeural", "+10%", "+0Hz"),
    ("en-US-BrianMultilingualNeural", "+10%", "+0Hz"),
    ("en-US-AvaMultilingualNeural", "+10%", "+0Hz"),
    ("en-US-EmmaMultilingualNeural", "+10%", "+0Hz"),
    ("en-US-ChristopherNeural", "+8%", "-2Hz"),
    ("en-US-EricNeural", "+10%", "+0Hz"),
    ("en-US-SteffanNeural", "+10%", "+0Hz"),
    ("en-US-RogerNeural", "+10%", "+0Hz"),
    ("en-US-AriaNeural", "+12%", "+2Hz"),
    ("en-US-MichelleNeural", "+12%", "+0Hz"),
    ("en-GB-RyanNeural", "+8%", "+0Hz"),
    ("en-GB-SoniaNeural", "+8%", "+0Hz"),
    ("en-AU-WilliamNeural", "+10%", "+0Hz"),
    ("en-IE-ConnorNeural", "+8%", "+0Hz"),
]


async def say(text, voice, rate, pitch, path):
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout or 0)


def main(out):
    os.makedirs("vs", exist_ok=True)
    segs, ass, t = [], [], 0.0
    for i, (v, rate, pitch) in enumerate(VOICES, 1):
        p = f"vs/{i:02d}.mp3"
        try:
            asyncio.run(say(LINE, v, rate, pitch, p))
        except Exception as e:
            print(f"::warning::{v} failed: {e}")
            continue
        d = dur(p) + 0.8
        segs.append((p, d))
        name = v.split("-")[2].replace("MultilingualNeural", "").replace("Neural", "")
        accent = {"en-US": "American", "en-GB": "British", "en-AU": "Australian", "en-IE": "Irish"}[v[:5]]
        s = lambda x: f"0:{int(x // 60):02d}:{x % 60:05.2f}"
        ass.append(f"Dialogue: 0,{s(t)},{s(t + d)},Big,,0,0,0,,{i}")
        ass.append(f"Dialogue: 0,{s(t)},{s(t + d)},Small,,0,0,0,,{name} · {accent}")
        t += d
    with open("vs/labels.ass", "w") as f:
        f.write("""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Big,Poppins,420,&H0000E5FF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,10,0,5,0,0,0,1
Style: Small,Poppins,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,2,0,0,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ass) + "\n")
    inputs, fl = [], []
    for k, (p, d) in enumerate(segs):
        inputs += ["-i", p]
        fl.append(f"[{k}:a]apad=whole_dur={d:.2f}[a{k}]")
    fl.append("".join(f"[a{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[a]")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                    "-f", "lavfi", "-i", f"color=c=0x11152E:s=1080x1920:r=30:d={t:.2f}",
                    "-filter_complex", ";".join(fl) + f";[{len(segs)}:v]ass=vs/labels.ass[v]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", out], check=True, stderr=subprocess.PIPE, text=True)
    print(f"::notice::sampler with {len(segs)} voices, {t:.0f}s")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as e:
        print(f"::error::{e!r}"[:500])
        raise
