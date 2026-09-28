import tempfile
import unittest
from pathlib import Path

from session_state import SessionState
from watcher import WatchScanner, WatchStore


class SessionAndWatcherTests(unittest.TestCase):
    def test_pending_session_round_trip_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store=SessionState(Path(temp)/'pending.json')
            self.assertEqual(store.load(),{})
            state={'paths':['C:/样例/a.txt','C:/样例/b'], 'selected_id':'abc','recursive':True,'extensions':'pdf'}
            store.save(state)
            self.assertEqual(store.load(),state)
            store.path.write_text('{broken',encoding='utf-8')
            self.assertEqual(store.load(),{})

    def test_watcher_waits_for_stability_and_retries_after_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'incoming'
            source.mkdir()
            file=source/'报告.txt'
            file.write_text('first',encoding='utf-8')
            watch={'id':'one','source':str(source),'profile_id':'dest','enabled':True}
            store=WatchStore(root/'watchers.json')
            store.save_watches([watch])
            self.assertEqual(store.load_watches(),[watch])
            now=[0]
            scanner=WatchScanner(settle_seconds=4,retry_seconds=60,clock=lambda:now[0])
            self.assertIsNone(scanner.ready([watch]))
            now[0]=5
            found=scanner.ready([watch])
            self.assertEqual(found[1],[str(file)])
            scanner.mark_attempted(*found)
            self.assertIsNone(scanner.ready([watch]))
            file.write_text('changed content',encoding='utf-8')
            now[0]=6
            self.assertIsNone(scanner.ready([watch]))
            now[0]=11
            self.assertEqual(scanner.ready([watch])[1],[str(file)])
            watch['enabled']=False
            self.assertIsNone(scanner.ready([watch]))


if __name__=='__main__':
    unittest.main()
