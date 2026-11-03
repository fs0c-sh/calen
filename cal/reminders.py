"""Desktop reminders.

Reminders are stored as data and fired with a fixed local notifier.
Reminder notes support simple mail-merge substitution for the standard
fields (title, start, location) — plain string replace, no templating
engine.
"""

import os
import subprocess

NOTIFIER = "/usr/bin/wall"

FIELDS = ("title", "start", "location")


def render_note(reminder):
    note = reminder.get("note", "")
    for key in FIELDS:
        value = str(reminder.get(key, ""))
        note = note.replace("{{ %s }}" % key, value)
        note = note.replace("{{%s}}" % key, value)
    return note


def fire(reminder):
    rendered = render_note(reminder)
    if os.path.exists(NOTIFIER):
        try:
            subprocess.run([NOTIFIER, rendered],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except OSError:
            pass
    return rendered
