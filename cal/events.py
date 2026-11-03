"""Calendar event model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Event:
    title: str
    start: datetime
    end: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)


def summarize(events):
    """One-line summaries, sorted by start time."""
    out = []
    for ev in sorted(events, key=lambda e: e.start):
        when = ev.start.strftime("%Y-%m-%d %H:%M")
        out.append("%s  %s" % (when, ev.title))
    return out
