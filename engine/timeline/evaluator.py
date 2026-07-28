"""Timeline evaluator — drives scene progression by firing events at scheduled times"""

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from engine.core.components import TimelineEvent, TimelineTrack


class TimelineEvaluator:
    """Evaluates a timeline, firing events at their scheduled times.
    
    The evaluator steps through time, firing any events whose time
    has been reached. Events can trigger actions on entities.
    """
    
    def __init__(self):
        self.tracks: Dict[str, TimelineTrack] = {}
        self.current_time: float = 0.0
        self.duration: float = 0.0
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.finished: bool = False
        self._fired_count: int = 0
    
    def load_timeline(self, timeline_data: dict) -> None:
        """Load timeline from parsed JSON/dict format.
        
        Expected format:
        {
            "scene_name": [
                {"time": 0.0, "action": "hero.idle", "params": {}},
                ...
            ]
        }
        """
        self.tracks = {}
        self.current_time = 0.0
        self.finished = False
        self._fired_count = 0
        
        for scene_name, events_data in timeline_data.items():
            events = []
            for ev in events_data:
                events.append(TimelineEvent(
                    time=float(ev.get("time", 0)),
                    action=ev.get("action", ""),
                    params=ev.get("params", {}),
                    fired=False
                ))
            track = TimelineTrack(
                name=scene_name,
                events=sorted(events, key=lambda e: e.time)
            )
            self.tracks[scene_name] = track
            
            # Update total duration
            if events:
                last_time = events[-1].time
                if last_time > self.duration:
                    self.duration = last_time
    
    def on(self, action_pattern: str, handler: Callable) -> None:
        """Register a handler for action patterns.
        
        Args:
            action_pattern: Action name like "hero.walk" or "*" for all
            handler: Callable(event_time, action_name, params)
        """
        if action_pattern not in self.event_handlers:
            self.event_handlers[action_pattern] = []
        self.event_handlers[action_pattern].append(handler)
    
    def seek(self, time: float) -> None:
        """Seek to a specific time, firing any events in the interval.
        
        Args:
            time: Target time in seconds
        """
        if time < self.current_time:
            # Rewind: reset all events, then seek forward
            for track in self.tracks.values():
                track.current_index = 0
                for ev in track.events:
                    ev.fired = False
            self.current_time = 0.0
            self._fired_count = 0
        
        self.step_to(time)
    
    def step_to(self, time: float) -> None:
        """Step forward to the given time, firing events along the way."""
        if time > self.duration:
            self.finished = True
            time = self.duration
        
        for track in self.tracks.values():
            while track.current_index < len(track.events):
                ev = track.events[track.current_index]
                if ev.time > time:
                    break
                if not ev.fired:
                    ev.fired = True
                    self._fire_event(ev)
                track.current_index += 1
        
        self.current_time = time
    
    def step(self, dt: float) -> None:
        """Advance time by delta, firing any events in the interval."""
        if self.finished:
            return
        self.step_to(self.current_time + dt)
    
    def _fire_event(self, event: TimelineEvent) -> None:
        """Dispatch an event to all registered handlers."""
        self._fired_count += 1
        
        # Split action into entity and action name
        parts = event.action.split(".", 1)
        action_name = parts[1] if len(parts) > 1 else event.action
        
        # Fire specific handlers
        if event.action in self.event_handlers:
            for handler in self.event_handlers[event.action]:
                handler(event.time, event.action, event.params)
        
        # Fire wildcard handlers
        if "*" in self.event_handlers:
            for handler in self.event_handlers["*"]:
                handler(event.time, event.action, event.params)
    
    def get_progress(self) -> float:
        """Get timeline progress as [0, 1]"""
        if self.duration <= 0:
            return 1.0
        return min(1.0, self.current_time / self.duration)
    
    def reset(self) -> None:
        """Reset timeline to beginning"""
        for track in self.tracks.values():
            track.current_index = 0
            for ev in track.events:
                ev.fired = False
        self.current_time = 0.0
        self.finished = False
        self._fired_count = 0
