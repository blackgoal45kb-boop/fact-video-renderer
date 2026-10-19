import os
import re
import subprocess
import textwrap
import time
import urllib.parse

import requests
import soundfile as sf
from kokoro_onnx import Kokoro

TITLE = os.environ["TITLE"]
SCRIPT = os.environ["SCRIPT"].strip()
SCENES = [s.strip() for s in os.environ["SCENES"].split("|") if s.strip()]
KEY = os.environ.get("POLLINATIONS_KEY", "")
VOICE = os.environ.get("VOICE", "af_heart")  # other good voices: af_bella, am_michael, bf_emma
W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(cmd):
    subprocess.run(cmd, check=True)


def make_image(prompt, idx):
    text = prompt + ", photorealistic, cinematic lighting, highly detailed, vertical, no text"
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(text)
    params = {"width": W, "height": H, "nologo": "true", "seed": 100 + idx}
    headers = {"Authorization": "Bearer " + KEY} if KEY else {}
    for _ in range(6):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                path = f"img{idx}.jpg"
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
        except requests.RequestException:
            pass
        time.sleep(20)  # anonymous tier is throttled, wait and retry
    raise RuntimeError(f"Image generation failed for scene {idx}")


sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]+", SCRIPT)] or [SCRIPT]
kokoro = Kokoro("kokoro.onnx", "voices.bin")

scene_files = []
for i, sentence in enumerate(sentences):
    img = make_image(SCENES[i % len(SCENES)], i)

    samples, sr = kokoro.create(sentence, voice=VOICE, speed=1.0, lang="en-us")
    wav = f"voice{i}.wav"
    sf.write(wav, samples, sr)
    dur = len(samples) / sr + 0.35
    frames = int(dur * FPS)

    with open(f"cap{i}.txt", "w", encoding="utf-8") as f:
        f.write(textwrap.fill(sentence, 24))

    step = 0.3 / frames
    if i % 2 == 0:
        z = f"min(zoom+{step:.6f},1.3)"
    else:
        z = f"if(eq(on,0),1.3,max(zoom-{step:.6f},1.0))"

    vf = (
        f"scale={W * 2}:{H * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
        "eq=contrast=1.08:saturation=1.15:brightness=0.02,"
        f"drawtext=textfile=cap{i}.txt:expansion=none:fontfile={FONT}:fontsize=62:fontcolor=white:"
        "borderw=5:bordercolor=black@0.9:line_spacing=14:x=(w-text_w)/2:y=h*0.68,"
        f"fade=t=in:st=0:d=0.3,fade=t=out:st={dur - 0.3:.3f}:d=0.3"
    )
    out = f"scene{i}.mp4"
    run([
        "ffmpeg", "-y", "-i", img, "-i", wav,
        "-vf", vf, "-af", "apad", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        out,
    ])
    scene_files.append(out)

with open("list.txt", "w") as f:
    for s in scene_files:
        f.write(f"file '{s}'\n")

run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
     "-movflags", "+faststart", "out.mp4"])
print("Rendered:", TITLE)
