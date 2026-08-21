# Recording the demo video

How to produce the silent screen capture that `doc/demo-narration.md` is spoken over.

Three files, three jobs, no overlap:

| File | Answers |
|---|---|
| `doc/demo-script.md` | What to say and what **not** to claim (live demo runbook) |
| `doc/demo-narration.md` | Where each beat falls in the finished video, with timecodes |
| **this file** | How to make the video: setup, exact clicks and inputs, the traps |

Target: **~6 minutes, silent, browser window only**, narrated live afterwards. Silent is
deliberate — one recording, many talks, and you can re-time the words without re-shooting.

---

## 1. Setup

Start the server **without `--reload`**. The reloader restarts on any file change and kills
in-flight upload tasks; the state file survives, so a page will spin forever on work that is
never coming back.

```bash
cd /path/to/wolfhack
FIT_HAPPENS_TEAM_PASSCODE=walkthrough \
  uv run uvicorn fit_happens.web.app:app --port 8010
```

Everything below runs from the disk cache, so no API spend and no network dependency. Add
`FIT_HAPPENS_OFFLINE=1` to force cache-only if the venue wifi is bad.

Then, in the browser:

1. Open `http://127.0.0.1:8010/hiring/sign-in` and enter the passcode once. The cookie carries
   the rest of the session. A bare `curl` to any `/hiring/*` URL returns **303 to sign-in** —
   that is normal, not a bug.
2. Maximise the window. Close every other tab so no tab strip clutter shows.
3. **Get the candidate portal token freshly — do not copy one from an old note.** Tokens are
   `sha256(secret:candidate_id)[:20]` and a rotated `.secret` silently invalidates every old
   link (an old link 404s):

   ```bash
   uv run python -c "
   from fit_happens.candidate.consent import ConsentStore
   s = ConsentStore('demo')
   for cid in ['rowan-feltz-6cb5cd', 'marcus_webb']:
       print(cid, '->', s.token_for(cid))"
   ```

   Rowan's portal is the one used in beat ③.

---

## 2. The capture command

Record **only the browser window**, never the full desktop.

Find the window's position and size first:

```bash
DISPLAY=:1 xdotool getwindowgeometry $(DISPLAY=:1 xdotool getactivewindow)
```

A maximised 1920x1080 window sits at `0,0`, and the page area starts ~32 px down (below the
browser chrome). So capture 1920x1048 from `+0,32`:

```bash
DISPLAY=:1 ffmpeg -y -f x11grab -framerate 25 -video_size 1920x1048 -i :1.0+0,32 \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  ~/Downloads/fit-happens-demo.mp4
```

**Stop it with SIGINT, never SIGKILL:**

```bash
pkill -INT -f x11grab
```

`SIGKILL` leaves the MP4 without its `moov` atom and the file will not play. Check the log ends
with `Exiting normally, received signal 2.`

### The infobar strip — fix it afterwards, not up front

While a browser-automation extension is attached, Chrome/Brave shows a *"…is debugging this
browser"* infobar. Its bottom **24 px** bleed into the top of the frame as a dark strip, and it
**appears and disappears during the recording** — so you cannot dodge it by shifting the capture
offset up front (shift down while the bar is absent and you crop off real page content instead).

Record the full region, then crop once at the end:

```bash
ffmpeg -y -i fit-happens-demo.mp4 -vf "crop=1920:1024:0:24" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -movflags +faststart out.mp4
```

If you record with no extension attached there is no bar and no crop is needed — check a frame
before assuming either way.

---

## 3. Pacing

The single biggest quality lever. On video:

- **Pause 3–5 s on every screen** before doing anything. It always feels too slow while you are
  doing it and reads as too fast on playback.
- **Never scroll with the mouse wheel.** Discrete ticks judder horribly. Scroll at a constant
  speed — either drag the scrollbar very steadily, or paste this into DevTools and call it:

  ```js
  window.S = (to, pps = 500) => new Promise(r => {
    const s = scrollY, d = to - s, u = Math.abs(d) / pps * 1e3;
    if (u < 16) { scrollTo(0, to); return r(scrollY); }
    const t0 = performance.now(), f = t => {
      const p = Math.min(1, (t - t0) / u);
      scrollTo(0, s + d * p);
      p < 1 ? requestAnimationFrame(f) : r(scrollY);
    };
    requestAnimationFrame(f);
  });
  // then: await S(3400, 500)   // scroll to y=3400 at 500 px/sec
  ```

  200–300 px/s reads as "deliberate", 500–700 px/s as "moving on". It must be re-pasted after
  every navigation.

---

## 4. The walk — exact clicks and inputs

Roughly 6 minutes at the pacing above.

### Beat ① — the ranking (~50 s)

1. `http://127.0.0.1:8010/hiring/role/demo` — hold 4 s on the table.
2. Scroll slowly to the bottom of the six rows (the page is only ~220 px taller than the
   viewport, so this is a short move). Hold 5 s on Daniel Kowalski at 3%.
3. Scroll back to the top. Hold 4 s.

### Beat ② — internal JD, the guard, the audit trail (~2 min 25 s)

4. Click **Internal JD: ON** → it reloads as **OFF**: *14 public requirements · 3 internal
   criteria withheld*, and the scores move. Hold 9 s.
5. Click **Internal JD: OFF** → back to **ON**: *17 requirements · 3 internal criteria applied*.
   Hold 5 s.
6. `http://127.0.0.1:8010/hiring/role/demo/edit` — hold 4 s, then scroll slowly to the bottom
   (**Private preferences**). Hold 4 s.
7. In the **first empty** preference row (rows 0–3 are already filled):
   - Set the type dropdown to **"Level the role is pitched at"**.
   - Click the text box and type `recent graduate`.
   - Wait — red **"Refused: age: age proxy"** appears under the box. Hold 8 s.
8. Select-all in the same box, delete, pause 2 s, then type `no career gaps`.
   Red **"Refused: socioeconomic proxy: career-gap screening - a proxy for parental leave,
   illness and disability"**. Hold 8 s.
9. `http://127.0.0.1:8010/hiring/role/demo/c/rowan-feltz-6cb5cd` — scroll slowly to the bottom.
   Hold 9 s on the **Audit trail** card: the four green checks, and the red
   *"internal constraint REFUSED"* line. **Do not click "Export everything we hold"** — it opens
   a download dialog on camera.

### Beat ③ — consent gates the fetch (~1 min)

10. `http://127.0.0.1:8010/apply/<rowan-token>` — hold 5 s on the status card.
11. Scroll slowly through **What we read from your CV** → **Things we could not work out** →
    **What we are allowed to look at**, pausing 4–5 s at each.
12. Stop where **Your public GitHub · SHARING** and the green **What that turned up** panel are
    both in frame — *CORROBORATED · Windows Server*, and the line about 24 other things not being
    held against them. Hold 10 s. This is the money shot of the beat.

### Beat ④ — the injection catch (~40 s)

13. `http://127.0.0.1:8010/hiring/role/demo/c/marcus_webb` — scroll slowly until the
    **Human review** card is in frame with the quoted injected text. Hold 10 s.
14. `http://127.0.0.1:8010/hiring/role/demo/integrity` — hold 9 s.

### Candidate side (~1 min 20 s)

15. `http://127.0.0.1:8010/` — the two-door landing. Hold 8 s.
16. `http://127.0.0.1:8010/jobs` — hold 5 s.
17. `http://127.0.0.1:8010/jobs/demo` — the clarity read (*80% specific · does not tell you:
    salary or band*) is already visible at the top. Hold 10 s, scroll down through the advert,
    scroll back up.
18. `http://127.0.0.1:8010/jobs/demo/apply` — hold 8 s. **Never fill or submit this form** — it
    creates a real candidate on the demo role.
19. `http://127.0.0.1:8010/hiring/role/demo` — end on the ranking. Hold 5 s, then stop ffmpeg.

**Never click** *Remove*, *Pass*, *Record and pass*, *Clear flags*, or *Stop sharing*. They all
mutate demo state and several are not one-click reversible.

---

## 5. Traps that cost time

These were all hit for real while producing the first cut.

- **A native `<select>` popup swallows synthetic clicks but not key presses.** If you drive the
  browser programmatically, clicking an option in an open dropdown does nothing — and stray
  arrow keys then land on whichever select last had focus, silently changing a *different* row.
  Reliable recipe: click the select (the popup opening looks good on camera), press **Escape**,
  then press **Down** N times. Focus stays on the closed select and each Down fires `change`.
  Driving it by hand with a real mouse has none of this problem.
- **The guard needs both halves.** `role_edit.html` only calls `/hiring/roles/check` when the
  type select **and** the text box are both non-empty. Type the text with the dropdown still on
  `—` and nothing happens — it looks like the guard is broken when it is simply not armed.
- **The refusal is debounced 350 ms** after the last keystroke. Pause at least a second before
  moving on, or you will cut away before it renders.
- **Scroll anchoring shifts the page** when the refusal message appears at the bottom of a
  scrolled-to-end document. If you are driving by coordinates, re-read positions after any
  content change rather than reusing the ones from before.
- **`/hiring/roles/check` is behind the passcode**, so testing it with `curl` gives 303, not a
  verdict. Test it from the browser console where the cookie is present.
- **Portal tokens rotate.** See §1.3. An old link 404s and it is not obvious why.

---

## 6. Check the result — actually look at it

`ffprobe` proves the file is well-formed. It does not prove the demo rendered. Do both.

```bash
# well-formed, right length, and decodes end to end with no errors
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,nb_frames \
  -of default=nw=1 out.mp4
ffmpeg -v error -i out.mp4 -f null -          # silence = clean decode

# contact sheet — one frame every 12 s, tiled, so you can eyeball every beat at once
ffmpeg -y -i out.mp4 -vf "select='not(mod(n\,300))',scale=390:-1,tile=6x6" -frames:v 1 sheet.png
```

Open `sheet.png` and confirm **every** beat is there and in order — short beats (the integrity
page, the apply form) are only ~9 s and fall between samples at coarser intervals, so drop to
`mod(n,150)` if one looks missing before concluding it is.

Check the top edge of a frame too, for the infobar strip from §2:

```bash
ffmpeg -y -ss 60 -i out.mp4 -frames:v 1 -vf "crop=1920:40:0:0,scale=960:-1" top.png
```
