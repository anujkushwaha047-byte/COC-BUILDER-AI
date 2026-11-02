# CoC Village Observer

A Windows desktop dashboard for read-only observation and planning during Clash
of Clans Hammer Jam. It captures the primary display in memory, attempts OCR of
visible HUD text, records compact observations in a local SQLite database, and
never clicks, types, or otherwise interacts with the game. Screenshots are not
stored.

## Run on Windows

1. Install Python 3.10 or later.
2. Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) and
   ensure `tesseract.exe` is on `PATH`. On Windows, it can also be installed with:

   ```powershell
   winget install --id UB-Mannheim.TesseractOCR --exact
   ```

3. From this project directory, run:

   ```powershell
   py -m pip install -r requirements.txt
   py main.py
   ```

This is a Tkinter desktop application, not a Node.js web project. Run it with
`py main.py`; `npm run dev` and a localhost URL do not apply.

Show the game on the primary display before launching. The dashboard observes
that display every five seconds. Close the dashboard to stop observation.

## Current recognition limits

HUD text and numbers are read with local Tesseract OCR. Resource readings are
only assigned when exactly four plausible numeric values appear in the upper
right HUD area; otherwise they remain unknown. Builder and Town Hall readings
are shown only when visible labels and counts can be associated confidently.
Upgrade timers are surfaced when OCR reads a timer-shaped token.

The current version intentionally does **not** infer building identity, levels,
obstacles, or collection indicators from unvalidated visual guesses. Such
fields remain unknown until a validated, locally run game-specific vision model
is added. Consequently, village completion and upgrade recommendations remain
unknown/empty when building data is unavailable. The recommendation engine
supports confidence-gated building candidates and applies the configured 50%
Hammer Jam discount only when a reliable cost and resource reading are present.

No account credentials are requested or accessed. There is no game-control,
anti-cheat bypass, or network integration.
