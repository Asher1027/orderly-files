import tempfile
import unittest
from pathlib import Path

from core import Organizer, plan


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'files'
        self.root.mkdir()
        self.engine = Organizer(Path(self.temp.name) / 'history')

    def put(self, name, content='sample'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_preview_is_read_only_and_skips_directories_and_temp(self):
        self.put('报告.pdf')
        self.put('sub/keep.txt')
        self.put('download.crdownload')
        p = plan(str(self.root))
        self.assertEqual(len(p['rows']), 1)
        self.assertTrue((self.root / '报告.pdf').exists())
        self.assertFalse((self.root / '文档').exists())

    def test_duplicate_move_and_undo_after_restart(self):
        self.put('报告.pdf', 'new')
        self.put('文档/报告.pdf', 'old')
        record = self.engine.execute(plan(str(self.root)))
        self.assertEqual((self.root / '文档/报告 (2).pdf').read_text(), 'new')
        self.assertEqual((self.root / '文档/报告.pdf').read_text(), 'old')
        engine = Organizer(self.engine.history_dir)
        self.assertEqual(engine.undo(engine.history()[0]), (1, []))
        self.assertEqual((self.root / '报告.pdf').read_text(), 'new')

    def test_new_collision_after_preview_never_overwrites(self):
        source = self.put('a.txt')
        preview = plan(str(self.root))
        self.put('文档/a.txt', 'precious')
        record = self.engine.execute(preview)
        self.assertEqual(record['items'][0]['status'], 'failed')
        self.assertTrue(source.exists())
        self.assertEqual((self.root / '文档/a.txt').read_text(), 'precious')

    def test_changed_source_is_skipped(self):
        source = self.put('a.txt')
        preview = plan(str(self.root))
        source.write_text('changed after preview')
        self.assertEqual(self.engine.execute(preview)['items'][0]['status'], 'failed')

    def test_undo_preserves_new_original_and_changed_destination(self):
        self.put('a.txt')
        record = self.engine.execute(plan(str(self.root)))
        self.put('a.txt', 'new original')
        count, errors = self.engine.undo(record)
        self.assertEqual(count, 0)
        self.assertTrue(errors)
        (self.root / 'a.txt').unlink()
        self.put('文档/a.txt', 'modified destination')
        self.assertEqual(self.engine.undo(record)[0], 0)

    def test_filter_and_month(self):
        self.put('a.JPG')
        self.put('b.txt')
        preview = plan(str(self.root), 'type_date', '.jpg')
        self.assertEqual(len(preview['rows']), 1)
        self.assertEqual(Path(preview['rows'][0]['target']).parent.parent.name, '图片')

    def test_interrupted_move_can_be_recovered(self):
        self.put('a.txt')
        record = self.engine.execute(plan(str(self.root)))
        record['items'][0]['status'] = 'pending'
        self.engine.save(record)
        self.assertEqual(self.engine.undo(self.engine.history()[0]), (1, []))

    def test_move_reports_per_file_progress(self):
        self.put('a.txt')
        self.put('b.txt')
        events=[]
        record=self.engine.execute(plan(str(self.root)),lambda completed,total,name:events.append((completed,total,name)))
        self.assertEqual(len(record['items']),2)
        self.assertEqual(events[0][0:2],(0,2))
        self.assertEqual(events[-1][0:2],(2,2))


if __name__ == '__main__':
    unittest.main()
