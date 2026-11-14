# Brag plan: AI Career Office, new office

## Answers
- **What is it:** a 3D office where four AI agents work on my move into an AI Engineer role through LinkedIn.
- **Who it's for / what it does:** me (and anyone job hunting in AI). Nora writes posts, Leo rewrites my LinkedIn profile, Maya finds jobs and people, Kai runs mock interviews.
- **What's new:** the office is rebuilt in Blender as four separate department offices off a glass corridor: Content Studio, Profile Lab, Scouting Desk, Coaching Room. Each office has its own colour, sign, board and props.
- **Most impressive claim:** each agent has its own office and its own board, and the whole building is generated from one Python script.
- **Visual hook:** the building blurred under "My AI agents got their own offices.", then sharp, with the four name tags popping in.
- **Real UI to show:** the running three.js app. Camera flights into each office, live activity lines on the name tags, and Morning standup bubbles over all four offices.
- **Tone:** `default` (punchy, clean, build in public).
- **Share caption:** "My AI agents got their own offices."

## Angle
"My AI agents got their own offices." A tour of the new building, captured frame by frame from the real app. Activity lines and the standup are mocked so no private data appears, and nothing is written to the database.

## Identity
Dark background `#1b1d23`, the app's system UI font, label chips `rgba(17,19,24,.86)`. Department colours: Content blue `#2563eb`, Profile green `#16a34a`, Scouting amber `#d97706`, Coaching purple `#9333ea`. 1920×1080, 30 fps, 21 s. Music at 120 BPM (one bar = 2 s); every cut lands on a bar.

## Storyboard (21 s)
| # | Time | Scene | On screen | Sound |
|---|---|---|---|---|
| 1 | 0.0–2.2 | Hook | Building blurred and dimmed. "My AI agents" / "got their own **offices.**" | Pad, riser |
| 2 | 2.2–6.0 | Reveal | Blur clears; the camera drifts around the building; name tags pop in one by one. Caption: "Four departments. One goal: my next AI engineer job." | Beat starts; four pitched pops |
| 3 | 6.0–14.0 | Tour | The camera flies into each office for 2 s: Content Studio → Profile Lab → Scouting Desk → Coaching Room. Each worker is busy (activity line on the tag). Caption card in the department colour: name + one line about what the agent does. | Whoosh per flight, soft pop per card |
| 4 | 14.0–18.0 | Standup | Back to the whole building; the cursor clicks "Morning standup"; a bubble pops up over each office. Caption: "Every morning, a standup across all four offices." | Click, four pops |
| 5 | 18.0–21.0 | Outro | Building dims. "AI Career Office" / four department chips / "Built in Blender · Claude Agent SDK · three.js". | Final chord |
