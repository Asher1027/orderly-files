"""Small, atomic store for the user's pending import session."""
import json
import os
from pathlib import Path


class SessionState:
    def __init__(self,path):
        self.path=Path(path)

    def load(self):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict):
                return {}
            paths=data.get('paths',[])
            data['paths']=[p for p in paths if isinstance(p,str)] if isinstance(paths,list) else []
            return data
        except (OSError,ValueError):
            return {}

    def save(self, data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(self.path)
