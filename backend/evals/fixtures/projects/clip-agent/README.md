# clip-agent

Turns long videos into short vertical clips.

- Transcribes the video locally with Whisper.
- A local Ollama model picks candidate moments from the transcript; Claude ranks them and writes the caption.
- ffmpeg cuts and reframes each clip to 9:16.

Status: works on my own recordings. Not released, no users yet, no benchmark numbers.
