"""
ingest.py  --  Multi-source ingestion. EVERY source normalizes to one Signal.
Add a new source = add one adapter. The extractor never changes.

Source -> reality (what you'd wire for production):
  PhoneCallAdapter   : 911 / ambulance / fire dispatch  -> Twilio Voice webhook -> Whisper STT
  RadioScannerAdapter: emergency radio                   -> SDR / Broadcastify   -> Whisper STT
  WeatherAdapter     : wind / humidity / red-flag        -> api.weather.gov (NOAA/NWS)
  RoadClosureAdapter : highway closures                  -> Caltrans 511 / QuickMap API
  FirePerimeterAdapter: active fire fronts               -> NASA FIRMS / CalFire API
  SocialAdapter      : crowd reports                     -> X/Twitter filtered stream

For the hackathon each adapter ships MOCK_DATA so the whole pipeline runs offline.
Replace .poll() bodies with real API/STT calls and nothing downstream changes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


@dataclass
class Signal:
    source: str       # "phone_call", "weather_api", ...
    channel: str      # "ambulance", "fire_dept", "NOAA", "Caltrans", ...
    text: str         # the raw human/text content the extractor reads
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta: dict = field(default_factory=dict)


class SourceAdapter:
    source = "generic"
    def poll(self) -> Iterable[Signal]:
        return []


class PhoneCallAdapter(SourceAdapter):
    """911 / ambulance / fire-dept calls. text == speech-to-text transcript."""
    source = "phone_call"
    MOCK = [
        ("ambulance", "Medic 4 on scene at the high school evac point, we have 6 casualties, need immediate transport, priority critical."),
        ("fire_dept", "Engine 12 reporting structure fire jumped Hwy 9 bridge, road is impassable, do not route units through there."),
        ("ambulance", "Rescue 7 at canyon road, multiple people stranded, 4 patients need evac."),
    ]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t, meta={"transcribed": True})


class RadioScannerAdapter(SourceAdapter):
    source = "radio"
    MOCK = [("dispatch", "All units be advised, river crossing washed out, mudslide debris on roadway.")]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t)


class WeatherAdapter(SourceAdapter):
    source = "weather_api"
    MOCK = [("NOAA", "Red flag warning: 35 mph gusts pushing fire toward Ridge Pass, visibility dropping from smoke.")]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t, meta={"wind_mph": 35})


class RoadClosureAdapter(SourceAdapter):
    source = "road_api"
    MOCK = [("Caltrans", "Route 4 CLOSED due to active fire front. No estimated reopening.")]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t, meta={"closure": True})


class FirePerimeterAdapter(SourceAdapter):
    source = "fire_api"
    MOCK = [("CalFire", "Perimeter update: coastal road now within active burn zone, treat as impassable.")]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t)


class SocialAdapter(SourceAdapter):
    source = "social"
    MOCK = [("twitter", "people at the north shelter reporting they need water and medical, lots of elderly #wildfire")]
    def poll(self):
        for ch, t in self.MOCK:
            yield Signal(self.source, ch, t)


class MultiSourceIngestor:
    """Aggregates every adapter into one stream of Signals."""
    def __init__(self, adapters=None):
        self.adapters = adapters or [
            PhoneCallAdapter(), RadioScannerAdapter(), WeatherAdapter(),
            RoadClosureAdapter(), FirePerimeterAdapter(), SocialAdapter(),
        ]
    def stream(self) -> Iterable[Signal]:
        for a in self.adapters:
            yield from a.poll()
