import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import Organizer, copy_move
from managed import Registry, transfer_plan, import_plan, safe_name, preset


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'inbox'
        self.source.mkdir()
        self.registry = Registry(self.base / 'settings.json')
        self.engine = Organizer(self.base / 'history')
        self.profile = {'id': 'one', 'name': '资料', 'path': str(self.base / 'library'), 'standard': '文件类型', 'rules': [{'name': '阅读', 'match': 'pdf,txt'}, {'name': '照片', 'match': '.jpg,png'}], 'fallback': '待分类'}
        self.registry.save(self.profile)

    def put(self, name, text='data'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_create_custom_structure_and_persist_multiple(self):
        root = Path(self.profile['path'])
        self.assertEqual({p.name for p in root.iterdir()}, {'阅读', '照片', '待分类'})
        second = dict(self.profile, id='two', path=str(self.base / 'second'))
        self.registry.save(second)
        self.assertEqual(len(Registry(self.registry.path).profiles), 2)
        self.registry.remove('one')
        self.assertTrue(root.is_dir())
        self.assertEqual(len(self.registry.profiles), 1)

    def test_folder_migration_and_persistent_undo(self):
        a = self.put('报告.pdf')
        b = self.put('image.PNG')
        c = self.put('unknown.xyz')
        preview = transfer_plan(self.profile, folder=str(self.source))
        self.assertEqual(len(preview['rows']), 3)
        self.assertTrue(a.exists())
        record = self.engine.execute(preview)
        self.assertTrue(all(i['status'] == 'moved' for i in record['items']))
        self.assertTrue((Path(self.profile['path']) / '照片/image.PNG').exists())
        self.assertEqual(self.engine.undo(self.engine.history()[0]), (3, []))
        self.assertTrue(all(p.exists() for p in (a, b, c)))

    def test_single_files_from_multiple_roots_and_dedup(self):
        a = self.put('a.txt')
        other = self.base / 'other'
        other.mkdir()
        b = other / 'b.pdf'
        b.write_text('test')
        preview = transfer_plan(self.profile, files=[str(a), str(b), str(a)])
        self.assertEqual(len(preview['rows']), 2)
        self.assertEqual(self.engine.undo(self.engine.execute(preview)), (2, []))

    def test_recursive_collision_and_filter(self):
        self.put('one/a.pdf', 'one')
        self.put('two/a.pdf', 'two')
        self.put('pic.png')
        shallow = transfer_plan(self.profile, folder=str(self.source))
        self.assertEqual(len(shallow['rows']), 1)
        recursive = transfer_plan(self.profile, folder=str(self.source), recursive=True, extensions='pdf')
        self.assertEqual({Path(r['target']).name for r in recursive['rows']}, {'a.pdf', 'a (2).pdf'})
        self.assertEqual(self.engine.undo(self.engine.execute(recursive)), (2, []))

    def test_keywords_priority_and_fallback(self):
        self.profile.update(standard='文件名关键词', rules=[{'name': '合同', 'match': '合同'}, {'name': '其他合同', 'match': '合同,协议'}])
        a = self.put('合同2026.pdf')
        b = self.put('notes.txt')
        preview = transfer_plan(self.profile, files=[str(a), str(b)])
        by_name = {Path(r['source']).name: Path(r['target']).parent.name for r in preview['rows']}
        self.assertEqual(by_name, {'合同2026.pdf': '合同', 'notes.txt': '待分类'})

    def test_date_rules_use_user_names(self):
        import os
        from datetime import datetime
        a = self.put('a.txt')
        timestamp = datetime(2025, 4, 15).timestamp()
        os.utime(a, (timestamp, timestamp))
        self.profile.update(standard='修改月份', rules=[{'name': '春季', 'match': '2025-03,2025-04'}])
        preview = transfer_plan(self.profile, files=[str(a)])
        self.assertEqual(Path(preview['rows'][0]['target']).parent.name, '春季')

    def test_reject_overlap_and_invalid_names(self):
        for folder in [self.profile['path'], str(self.base), str(Path(self.profile['path']) / '阅读')]:
            with self.assertRaises(ValueError):
                transfer_plan(self.profile, folder=folder)
        for name in ['../outside', 'a/b', 'CON', 'a.', 'a:b']:
            with self.assertRaises(ValueError):
                safe_name(name)
        invalid = dict(self.profile, rules=[{'name': '../escape', 'match': 'txt'}])
        with self.assertRaises(ValueError):
            self.registry.save(invalid)

    def test_copy_fallback_verifies_and_undoes_different_identity(self):
        a = self.put('cross.txt', 'across volumes')
        preview = transfer_plan(self.profile, files=[str(a)])
        with patch('core.move_exclusive', side_effect=copy_move):
            record = self.engine.execute(preview)
            self.assertEqual(record['items'][0]['status'], 'moved')
            self.assertNotEqual(record['items'][0]['signature'][3], record['items'][0]['target_signature'][3])
            self.assertEqual(self.engine.undo(record), (1, []))
        self.assertEqual(a.read_text(), 'across volumes')

    def test_copy_failure_preserves_source_and_existing_target(self):
        a = self.put('a.txt', 'original')
        dest = self.base / 'existing.txt'
        dest.write_text('existing')
        with self.assertRaises(FileExistsError):
            copy_move(a, dest)
        self.assertEqual(a.read_text(), 'original')
        self.assertEqual(dest.read_text(), 'existing')
        dest = self.base / 'partial.txt'
        with patch('core.shutil.copyfileobj', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                copy_move(a, dest)
        self.assertTrue(a.exists())
        self.assertFalse(dest.exists())

    def test_cross_volume_interruption_recovery(self):
        a = self.put('a.txt')
        with patch('core.move_exclusive', side_effect=copy_move):
            record = self.engine.execute(transfer_plan(self.profile, files=[str(a)]))
        item = record['items'][0]
        item['status'] = 'pending'
        item.pop('target_signature')
        self.assertEqual(self.engine.undo(record), (1, []))

    def test_already_classified_file_is_skipped(self):
        path = Path(self.profile['path']) / '阅读/a.txt'
        path.write_text('data')
        self.assertEqual(transfer_plan(self.profile, files=[str(path)])['rows'], [])

    def test_duplicate_profile_and_case_insensitive_names_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.save(dict(self.profile, id='two'))
        with self.assertRaises(ValueError):
            self.registry.save(dict(self.profile, rules=[{'name': 'PDF', 'match': 'pdf'}, {'name': 'pdf', 'match': 'txt'}]))

    def test_mixed_batch_drop_collision_dedup_and_undo(self):
        a=self.put('拖入 目录/a.txt','one')
        b=self.put('另一个目录/a.txt','two')
        c=self.put('单独 文件.pdf','three')
        preview=import_plan(self.profile,[str(a.parent),str(b.parent),str(c),str(a)],recursive=True)
        self.assertEqual(len(preview['rows']),3)
        self.assertEqual(len({r['target'].casefold() for r in preview['rows']}),3)
        record=self.engine.execute(preview)
        self.assertTrue(all(r['status']=='moved' for r in record['items']))
        self.assertEqual(self.engine.undo(record),(3,[]))
        self.assertEqual(a.read_text(),'one')
        self.assertEqual(b.read_text(),'two')

    def test_invalid_drop_is_read_only(self):
        a=self.put('a.txt')
        with self.assertRaises(ValueError):
            import_plan(self.profile,[str(a),str(self.base/'missing')])
        self.assertTrue(a.exists())
        self.assertFalse((Path(self.profile['path'])/'阅读/a.txt').exists())


if __name__ == '__main__':
    unittest.main()
