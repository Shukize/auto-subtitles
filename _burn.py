import os
os.environ["QT_QPA_PLATFORM"]="offscreen"
from subtitle_studio import config
from subtitle_studio.core import media, subtitles
from subtitle_studio.core.transcribe import Cue, TranscriptionResult

res = TranscriptionResult(cues=[Cue(0.2,2.9,"The quick brown fox\njumps over the lazy dog."),
                                Cue(4.0,6.2,"Subtitle Studio is working correctly.")],
                          language="en", duration=7.0)
doc = subtitles.SubtitleDocument.from_result(res)
style = config.SubtitleStyle(font_name="Arial", font_size=28, bold=True,
                             primary_color="#FFFF00", outline_color="#000000",
                             outline=2.5, alignment=2, margin_v=30)
ass = os.path.abspath("_burn.ass")
doc.save_styled_ass(ass, style)
print("ass written:", os.path.exists(ass))
out = os.path.abspath("_testvid_subtitled.mp4")
prog=[]
media.burn_subtitles(os.path.abspath("_testvid.mp4"), ass, out,
                     progress=lambda f: prog.append(f), duration=7.0)
print("burned:", os.path.exists(out), "size:", os.path.getsize(out), "progress_max:", round(max(prog),2) if prog else None)
