# Bytehound — Long-Run Logging Guide for Test Labs

How to set up a PC and Bytehound for BMS tests that log continuously for
days, weeks or months, and what to do during and after the test.

---

## 1. Prepare the PC (once per test bench)

Most data loss in long tests comes from the PC, not the BMS: sleep, USB
power saving and updates interrupt the serial link.

| Setting | Where | Value |
|---|---|---|
| Power plan | Control Panel → Power Options | **High performance** (or Ultimate) |
| Sleep / hibernate | Power Options → Change plan settings | **Never** (on battery and plugged in) |
| USB selective suspend | Power Options → Advanced → USB settings | **Disabled** |
| USB adapter power saving | Device Manager → the USB-serial adapter → Power Management | Untick *Allow the computer to turn off this device* |
| USB root hubs | Device Manager → Universal Serial Bus controllers → each *USB Root Hub* → Power Management | Untick *Allow the computer to turn off this device* |
| Windows Update | Settings → Windows Update | **Pause updates** for the test duration (or set active hours covering 24 h) |
| Antivirus | Your antivirus settings | Exclude the log folder and `Bytehound.exe` from real-time scanning |
| Screen saver / lock | Personalisation | May stay on — Bytehound keeps logging while locked |

Hardware:

- Connect the USB-serial adapter **directly** to the PC (no unpowered hub).
  Use a short, good-quality cable.
- Keep the adapter on the same USB port so its COM number does not change.
- Use a UPS for the PC if power cuts are possible.

## 2. Plan disk space

Bytehound never deletes data. Size the log drive before the test.

**Measure, don't guess:** run the real setup for one hour, stop logging, and
open `session.json` in the session folder. Each segment lists its file sizes
under `"bytes"`. Multiply the total of one hour-long segment by 24 for a day.

Rough estimate per day of logging:

| Part | Size per day |
|---|---|
| Event log CSV | rows per second × ~(60 + 7 × signals) bytes × 86,400 |
| Event log `.xlsx` | about half the CSV |
| Analysis data (`*_analysis.npz`) | 5–100 % of the CSV (smooth signals compress well) |
| Raw capture `.bhraw` | bytes per second on the wire × 86,400 (≤ ~1 GB/day at 115,200 baud) |
| Fixed-step log (if on) | same formula as the event log, rows = 1 / step |

Example: 10 cycles/s, 50 signals → about 0.4 GB/day event CSV, 1.5–2 GB/day
in total with all files. Keep at least **2× the expected total free**.

The disk guard warns below 10 GB free and stops logging cleanly below 2 GB
(both adjustable in *Tools → Logging Settings*).

## 3. Configure Bytehound

1. **Load the configuration** for the BMS (*File → Import Config*).
2. **Connect** (*Device → Connect*). In the Connect dialog:
   - set the COM port and baud rate;
   - tick **Auto-reconnect on disconnect** — essential for long tests: a USB
     glitch then becomes a short recorded gap instead of the end of the log.
3. If the BMS is polled, start **Auto-Fetch** and choose the targets. After
   a reconnect, Bytehound restores the same Auto-Fetch setup by itself.
4. **Tools → Logging Settings**:
   - *New segment every*: 60 min is a good default;
   - *Event log*: on;
   - *Fixed-step log*: on if the test needs one row every N seconds (for
     example to align with a cycler or climate chamber), with the step;
   - *Stale after*: how many steps old a value may be before it counts as
     stale (default 3); choose *Hold last value* or *Leave blank*;
   - disk warning / stop levels.
5. **Device → Start Logging** and name the session (a folder is created).

## 4. During the test

The status bar shows everything that matters:

| Indicator | Meaning | Action |
|---|---|---|
| `Logging: <session> · segment N · X GB free` | Recording normally | none |
| `Logging: … · waiting for reconnect` | Device disconnected; logging continues and resumes in a new segment when it is back | check the cable / BMS power |
| `Discarded: N B` (and amber ⚠ badge) | Received bytes that were not valid frames after the first good one: noise or wrong settings | check wiring, baud rate, protocol config; hover the badge |
| `Driver errors: N` | The serial driver / USB adapter lost or corrupted bytes before Bytehound got them | check cable, USB power settings (section 1), adapter quality |
| `Errors: N` | Frames with a bad CRC (kept in `seg_NNNN_rejected.csv`) | occasional is normal noise; a steady rise means wiring or baud problems |
| ⚠ *Log drive is getting full* | Below the warning level | free space or prepare another drive |

Leave the PC alone during the test. Do not unplug the adapter unless needed.
Opening the session in the Analysis Suite while it records is fine — it
shows the segments closed so far.

## 5. After the test

1. **Device → Stop Logging.** Finishing the last segment takes a few seconds.
   If the decoded log could not keep up at some point, Bytehound offers to
   rebuild it from the raw capture — answer **Yes**.
2. The session folder contains, per segment, the event log (CSV + Excel),
   the fixed-step log if enabled, rejected frames, and the raw capture, plus
   `session.json` and a copy of the configuration.
3. **Analyse:** *Tools → Analysis Suite → File → Open Logging Session…*.
   Any length opens in seconds; zoom in for full detail. Statistics and
   exports always use every recorded sample.
4. **Archive the whole folder.** To check a copy is intact, compare files
   with the SHA-256 checksums listed per segment in `session.json`.

## 6. If the PC crashed or lost power

Restart Bytehound. Unfinished sessions are completed automatically at
start-up (a message appears in the Activity Log). Everything written up to
the moment of the crash is kept; the session is marked *recovered* in
`session.json`. Start a new logging session to continue the test.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Gaps every few minutes/hours | USB power saving, sleep | Section 1 settings |
| Logging stopped by itself | Disk below the stop level | Free space; restart logging |
| No data after a reconnect | Device not answering | Check BMS power; Auto-Fetch is restored automatically |
| Many rejected frames / discarded bytes | Wrong baud rate, noise, wrong protocol config | Check settings and wiring |
| Driver errors | Cable, adapter, USB port | Replace cable, use another port/adapter |
| Analysis Suite asks to prepare data | Older or recovered session | Let it finish once; it is saved for next time |
