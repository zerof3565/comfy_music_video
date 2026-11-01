# 999doahong

> Source: Gemini 3.8 Flash — Google AI Studio (Temporary chat)
> Input: 999doahong.mp3 (0:13.032)
> Prompt: "no lipsync script"
> AI Studio response: 1st
> System instructions preset: Film Director

---

### Step 1: Visual Continuity Reference Prompts (Midjourney / Flux)

#### Integrated Character Turnaround Sheet

```text
4-panel horizontal turnaround sheet, full-length shots: front view, 90-degree profile, 45-degree angle, back view. A 32-year-old East Asian man with sharp jawline, short swept-back damp black hair, and tired, melancholic eyes. Wearing a tailored charcoal wool trench coat over a high-neck black ribbed sweater, dark pleated trousers, and polished black oxfords. Neutral standing pose, blank studio cyclorama background, uniform soft lighting, highly detailed fabric weave and facial textures --ar 16:9
```

#### Dynamic Entity / Key Prop Sheet

```text
Multi-angle reference sheet of a heavy-bottomed vintage faceted crystal rocks glass containing two fingers of amber whiskey and a single melting clear ice cube. Photographed against neutral studio grey, edge-lit to capture glass refractions and liquid clarity --ar 16:9
```

#### Environment Turnaround Sheet (4-View Cardinal Grid)

```text
4-view cardinal perspective grid (0° Front, 90° Right, 180° Reverse, 270° Left) of a dim, rainy 1990s neon-lit bar interior. 0°: Rain-streaked window overlooking hazy neon signs; 90°: Dark mahogany counter with vintage spirits; 180°: Velvet booth seating and entrance door; 270°: Brass-framed mirror wall reflecting soft amber lighting. Consistent diffuse atmospheric haze and warm tungsten glow across all panels --ar 16:9
```

---

### Step 2: Grounded Cinematic Storyboard

#### Story Beats & Emotional Progression

- 00:00 - 00:06: Solitary stillness. Character sits by the rain-streaked window, shoulders dropped, staring unfocused into the distant city lights.
- 00:06 - 00:12: Micro-action of suppression. He reaches for the rocks glass, lifts it slowly, pauses near his chest as his jaw clenches, and sets it down without drinking, watching the condensation roll down the glass.

#### Layered Audio Design

- Dialogue & Lip Motion: None (no lipsync; silent acting, mouth closed).
- Diegetic Foley: Heavy crystal clinking on wood, coat sleeve rustling against tabletop, faint liquid slosh.
- Environmental Room Tone: Continuous muffled exterior rain, low wind buffeting the windowpane, low hum of neon ballast.
- Non-Diegetic Score: Slow melancholic Chinese ballad with nylon-string acoustic guitar and soft strings. The provided vocal track enters at 00:00, expressing sorrow over fading memories.

---

### Step 3: MiniMax Generation Prompts (Ref2VA Full-Reference Mode)

#### Clip 1 [00:00 - 00:12 | Duration: 12s]

- Clips & Context: Clip 1 of 1. Complete melancholic vignette establishing the character's emotional isolation without spoken dialogue.
- Head/Tail Transitions: Head: Hard cut | Tail: Dissolve to black

```text
subject_definitions:
<Subject 1> is the 32-year-old East Asian man wearing a charcoal wool trench coat and black ribbed sweater, mapped to <Picture 1>.
<Subject 2> is the rain-streaked window booth inside the retro amber-lit bar, mapped to <Picture 2>.
<Picture 1> is the character turnaround sheet establishing <Subject 1>'s facial likeness, hairstyle, and wardrobe.
<Picture 2> is the 4-view environment reference sheet establishing the bar interior and rain-streaked glass.
<Audio 1> is the non-diegetic vocal track ("往事如风... 痴情只是难懂... 借酒相送... 送不走身影朦胧").

summary:
[reference generation + audio reference] A 12-second cinematic sequence tracking a solitary man at a rain-slicked window table inside a dim tavern. The generation maintains continuous visual fidelity from <Picture 1> and atmospheric coherence from <Picture 2> synchronized to <Audio 1>, featuring purely physical acting without any spoken dialogue or lipsync.

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - Facial anatomy, swept-back damp hair, and charcoal trench coat texture strictly maintained.
<Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - Mahogany wood tones, amber neon reflections, and rain droplet patterns fully preserved.
<Picture 1>: fully_copy - Baseline character identity and costume details directly transferred.
<Picture 2>: reference - Architectural fixtures, palette, and lighting setup preserved.
<Audio 1>: reference - Paces the narrative cutting points and actor's deliberate, measured pauses.

detailed_description:
Cinematic 35mm film aesthetic, shallow depth of field, anamorphic blue-amber chromatic palette. No spoken dialogue; lips remain closed.
[Shot 1] The scene opens on <Subject 1> seated beside <Subject 2>'s wet glass window. The camera pushes in with small amplitude at slow speed toward <Subject 1>, who stares silently into the rain with heavy eyelids, his breath lightly fogging the cold glass.
[Shot 2] At 00:06.500, the camera cuts to a medium close-up profile. The camera tracks right with small amplitude at slow speed as <Subject 1> lowers his gaze, curls his fingers around the heavy crystal glass, lifts it two inches from the table, hesitates with tight jaw tension, and rests it back onto the damp wood without taking a sip.

overall_soundscape:
Low rumble of distant thunder, rhythmic rainfall pattering against glass, a subtle low-frequency hum of a neon transformer, and the sharp dull thud of a heavy glass touching wood.

non_diegetic_music:
A gentle, melancholic Mandarin vocal ballad supported by fingerpicked acoustic guitar and warm, lingering cello pads playing at 68 BPM.
```
