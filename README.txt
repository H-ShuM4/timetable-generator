===========================================================================
  Timetable Generator
===========================================================================

This system builds class timetables for the Faculty of Business
Administration, the Faculty of Accounting, and the Junior College Division,
from the curriculum and teacher Excel files the office already maintains.


---------------------------------------------------------------------------
  BEFORE YOU START
---------------------------------------------------------------------------

Python 3.11 or newer must be installed on this computer.

  1. Download it from  https://www.python.org/downloads/windows/
  2. During installation, tick "Add python.exe to PATH".

If Python is missing, setup.bat will tell you and stop.


---------------------------------------------------------------------------
  FIRST-TIME SETUP  (once per computer)
---------------------------------------------------------------------------

  Double-click  setup.bat

This creates a local Python environment inside this folder and installs
everything the system needs. It downloads roughly 350 MB, so it may take
several minutes. An internet connection is required for this step only.

When it finishes it will say "Setup complete."


---------------------------------------------------------------------------
  DAILY USE
---------------------------------------------------------------------------

  Double-click  start.bat

A black console window opens and your browser opens the system at
http://localhost:8000/

Keep the console window open while you use the system.
To stop the server, close the console window or press Ctrl+C in it.

If port 8000 is already taken, start on another port from a command
prompt in this folder:

  start.bat 8001


---------------------------------------------------------------------------
  USING THE SYSTEM
---------------------------------------------------------------------------

  1. FILE LOADING
     Drag the curriculum and teacher Excel files onto the page. The system
     reports how many subjects and teachers it read, and lists any problems
     it found in the data. Warnings do not stop generation.

  2. GENERATE
     Choose a mode and press the generate button.

       Mock          - no AI. Uses the built-in solver only.
                       Selected automatically when no API key is set.
       Optimization  - uses Google Gemini, then the solver for anything
                       left over. Requires an API key (see SETTINGS).
       Inherit       - reuses last year's timetable and only rearranges
                       teachers whose availability or research day changed.
                       Requires last year's files as well.

     The log panel at the bottom shows each stage as it happens.
     A full run takes about one minute.

  3. RESULT
     Review the timetable by faculty and term. Drag a class to move it.
     A move that would break a rule is refused with the reason.
     Press the export button to download the timetable as Excel.

  4. SETTINGS
     Store the Gemini API key, choose the model, and set how many times
     to retry a failed request. The key is stored on this computer only
     and is never shown again in full after saving.


---------------------------------------------------------------------------
  WHERE THINGS ARE STORED
---------------------------------------------------------------------------

  backend\.env                 the Gemini API key
  backend\data\settings.json   model name and retry count
  backend\data\sessions\       generated timetables, one file per run
  backend\logs\                a log file per run, for troubleshooting

These are created automatically the first time they are needed.
None of them are included in this package.


---------------------------------------------------------------------------
  IF SOMETHING GOES WRONG
---------------------------------------------------------------------------

  "Python was not found"
      Install Python and tick "Add python.exe to PATH", then run setup.bat.

  "a .venv folder exists but was not built for Windows"
      This folder was copied from another computer. Delete the .venv
      folder and run setup.bat again.

  "port 8000 is already in use"
      The system may already be running - look for another console window.
      Otherwise start on a different port:  start.bat 8001

  Generation finishes but some subjects are unplaced
      The result screen lists them with their names and teachers. This
      usually means a part-time teacher is assigned more classes in a term
      than their stated availability allows. The timetable cannot solve
      that; the teacher's available days or their assignment must change.

  Anything else
      The log file for the run is in backend\logs\, named by date and time.
      It records what each stage did.
