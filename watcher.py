"""Opt-in source-folder monitoring while the desktop app is open."""
import os
import time
from pathlib import Path

from session_state import SessionState


class WatchStore(SessionState):
    def load_watches(self):
        try:
            import json
            data=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            return []
        if not isinstance(data,list):
            return []
        return [w for w in data if isinstance(w,dict) and isinstance(w.get('id'),str) and isinstance(w.get('source'),str) and isinstance(w.get('profile_id'),str)]

    def save_watches(self,watches):
        # SessionState's atomic writer accepts any JSON data.
        self.save(watches)


class WatchScanner:
    def __init__(self,settle_seconds=4,retry_seconds=60,clock=time.monotonic):
        self.settle_seconds=settle_seconds
        self.retry_seconds=retry_seconds
        self.clock=clock
        self.observed={}
        self.attempted={}

    def ready(self,watches):
        """Return at most one configured source and its unchanged, settled files."""
        now=self.clock()
        found=[]
        live=set()
        for watch in watches:
            if not watch.get('enabled',False):
                continue
            source=Path(watch['source'])
            if source.is_symlink() or getattr(source,'is_junction',lambda:False)() or not source.is_dir():
                continue
            candidates=[]
            try:
                entries=list(os.scandir(source))
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith('.') or Path(entry.name).suffix.lower() in {'.tmp','.part','.crdownload'}:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat=entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                key=(watch['id'],os.path.normcase(entry.path))
                live.add(key)
                sig=(stat.st_size,stat.st_mtime_ns)
                previous=self.observed.get(key)
                if previous is None or previous[0]!=sig:
                    self.observed[key]=(sig,now)
                    self.attempted.pop(key,None)
                    continue
                last=self.attempted.get(key)
                if now-previous[1]>=self.settle_seconds and (last is None or now-last>=self.retry_seconds):
                    candidates.append(entry.path)
            if candidates:
                found.append((watch,candidates[:50]))
        for key in list(self.observed):
            if key not in live:
                self.observed.pop(key,None)
                self.attempted.pop(key,None)
        return found[0] if found else None

    def mark_attempted(self,watch,paths):
        now=self.clock()
        for path in paths:
            self.attempted[(watch['id'],os.path.normcase(path))]=now
