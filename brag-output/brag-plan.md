# Brag plan: AI Career Office

## Answers
- **What is it:** a 3D office where four AI agents work on my move into an AI Engineer role through LinkedIn.
- **Who it's for / what it does:** me (and anyone job hunting in AI): Nora writes posts, Leo rewrites my LinkedIn profile, Maya finds jobs and people, Kai runs mock interviews. Click a worker to talk.
- **What sets it apart:** the job search is a place, not a chat box. Workers sit at desks, show what they're doing, keep working while you're elsewhere, and hold a morning standup from their boards.
- **Most impressive claim:** four agents with real tools, sharing one career profile, all on my Claude plan.
- **Visual hook:** the office itself: blurred, then sharp, with the four name tags popping in.
- **Real UI to show:** click Nora → camera flies in → "Weekly brief" → "Searching the web…" → reply streams; workers busy in the background → green "Has something for you"; Morning standup bubbles over every head.
- **Tone:** `default` (punchy, clean, build in public).
- **Share caption:** "My job search has an office: four AI agents at four desks."

## Angle
"My job search has an office." Everything shown is the running app, captured frame by frame from the real three.js scene and UI. Chat replies, standup lines and the chat history are mocked so no private data appears, and nothing is written to the database.

## Identity
Dark office background `#1b1d23`, system UI font (the app's), label chips `rgba(17,19,24,.82)`, blue `#2563eb`, standup green `#166534`, activity yellow `#fcd34d`, news green `#22c55e`. 1920×1080, 30 fps, 21 s. Music at 120 BPM (one bar = 2 s); every cut lands on a bar.

## Storyboard (21 s)
| # | Time | Scene | On screen | Sound |
|---|---|---|---|---|
| 1 | 0.0–2.0 | Hook | Office blurred and dark. "My job search" / "has an office." types in big by 0.7 s, holds. | Pad + soft kick in |
| 2 | 2.0–6.0 | Reveal | Blur clears; name tags pop in one by one (Nora, Leo, Maya, Kai, 0.35 s apart). Caption: "Four AI agents. One goal: my next AI engineer job." | Full beat starts; four pitched pops for the tags |
| 3 | 6.0–10.0 | Talk to a worker | Cursor clicks Nora → camera flies in → chat opens → clicks "Weekly brief" → tag reads "Searching the web…" → reply streams. Caption: "Click a worker to talk." | Click, whoosh on the flight, soft ticks while typing |
| 4 | 10.0–14.0 | Background work | Overview. Maya "Searching the web…", Kai "Setting up the interview…". Replies land → green "Has something for you" pills. Caption: "They keep working while you're elsewhere." | Two chimes for the pills |
| 5 | 14.0–18.0 | Standup | Cursor clicks "Morning standup" → panel opens, a bubble pops over each worker's head. Caption: "Every morning, a standup." | Click, four pops |
| 6 | 18.0–21.0 | Outro | Office dims. "AI Career Office" / "Four AI agents for my LinkedIn job search" / "Claude Agent SDK · FastAPI · three.js". | Final chord, ring out |
