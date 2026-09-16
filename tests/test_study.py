import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
from core import Store


class Tab:
    def __init__(self):
        self.current = 'library'
    def select(self, tab=None):
        if tab is not None:
            self.current = str(tab)
        return self.current


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.spawn_speech = patch.object(app.subprocess, 'Popen').start()
        self.addCleanup(patch.stopall)
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.ui = app.App.__new__(app.App)
        self.ui.store = self.store
        self.ui.tabs = Tab()
        self.ui.library, self.ui.study = 'library', 'study'
        self.ui._last_tab = 'library'
        self.ui.worker = Mock()
        self.ui.worker.poll.return_value = None
        self.ui.signature = None
        self.ui.root = Mock()
        self.ui.study_count = Mock()
        self.ui.study_count.get.return_value = '20'
        self.ui.count_input = Mock()
        self.ui.refresh = self.store.reload
        for name in ('progress', 'bar', 'english', 'chinese', 'hint', 'yes', 'no'):
            setattr(self.ui, name, Mock())
        self.ui.render_card()

    def tearDown(self):
        self.tmp.cleanup()

    def words(self, count):
        ids = [self.store.add(f'word {i}', f'释义 {i}')[0] for i in range(count)]
        self.store.reload()
        return ids

    def enter(self):
        self.ui.tabs.select('study')
        self.ui.on_tab_changed()

    def test_nine_ready_words_start_on_tab(self):
        ids = self.words(9)
        self.enter()
        self.assertEqual(set(self.store.queue), set(ids))
        self.assertEqual((self.store.done, self.store.total), (0, 9))
        self.ui.yes.configure.assert_called_with(state='normal')

    def test_twenty_max_unique_and_excludes_untranslated(self):
        ids = self.words(27)
        bad, _ = self.store.add('not translated')
        self.enter()
        self.assertEqual(len(self.store.queue), 20)
        self.assertEqual(len(set(self.store.queue)), 20)
        self.assertTrue(set(self.store.queue).issubset(ids))
        self.assertNotIn(bad, self.store.queue)

    def test_existing_round_and_progress_preserved(self):
        ids = self.words(5)
        self.store.start(ids)
        self.store.answer(True)
        before = (list(self.store.queue), self.store.done, self.store.total)
        self.enter()
        self.assertEqual((self.store.queue, self.store.done, self.store.total), before)

    def test_click_reveals_chinese_and_poll_does_not_hide_it(self):
        self.words(3)
        self.enter()
        current = next(w for w in self.store.words if w['id'] == self.store.queue[0])
        self.assertNotEqual(self.ui.chinese.configure.call_args.kwargs['text'], current['zh'])
        self.ui.reveal()
        self.assertEqual(self.ui.chinese.configure.call_args.kwargs['text'], current['zh'])
        count = self.ui.chinese.configure.call_count
        self.ui.poll()
        self.assertEqual(self.ui.chinese.configure.call_count, count)

    def test_unknown_rotates_known_removes_and_restores(self):
        self.words(3)
        self.enter()
        before = list(self.store.queue)
        self.ui.answer(False)
        self.assertEqual(self.store.queue, before[1:] + before[:1])
        self.assertFalse(self.ui.revealed)
        self.ui.answer(True)
        restored = Store(self.tmp.name)
        self.assertEqual(restored.queue, before[2:] + before[:1])
        self.assertEqual(restored.done, 1)
        self.assertEqual(len(restored.words), 3)

    def test_completion_stays_complete_until_reentering(self):
        self.words(1)
        self.enter()
        self.ui.answer(True)
        self.ui.poll()
        self.assertEqual(self.store.queue, [])
        self.assertEqual(self.store.done, 1)
        self.ui.yes.configure.assert_called_with(state='disabled')
        self.ui.tabs.select('library')
        self.ui.on_tab_changed()
        self.enter()
        self.assertEqual((self.store.done, len(self.store.queue)), (0, 1))

    def test_empty_collection_no_dialog_or_error(self):
        with patch.object(app.messagebox, 'showinfo') as dialog:
            self.enter()
            self.ui.poll()
            dialog.assert_not_called()
        self.assertEqual(self.store.queue, [])
        self.ui.yes.configure.assert_called_with(state='disabled')

    def test_translation_finishes_while_empty_study_page_open(self):
        wid, _ = self.store.add('pending')
        self.enter()
        self.assertEqual(self.store.queue, [])
        job = self.store.claim()
        self.store.finish(job, zh='等待')
        self.ui.poll()
        self.assertEqual(self.store.queue, [wid])

    def test_manual_selection_only_uses_selected_ready_words(self):
        ids = self.words(5)
        pending, _ = self.store.add('pending')
        self.ui.tree = Mock()
        self.ui.tree.selection.return_value = [ids[1], ids[3], pending]
        self.ui.selected_set()
        self.assertEqual(self.store.queue, [ids[1], ids[3]])

    def test_new_collection_during_study_does_not_replace_queue(self):
        self.words(4)
        self.enter()
        before = list(self.store.queue)
        Store(self.tmp.name).add('new collection', '新的收藏')
        self.ui.poll()
        self.assertEqual(self.store.queue, before)
        self.assertEqual(len(self.store.words), 5)

    def test_card_click_speaks_current_english_as_literal_argument(self):
        self.store.add('--file harmless text', '测试释义')
        self.enter()
        self.ui.reveal()
        self.assertEqual(self.spawn_speech.call_args.args[0],
                         ['/usr/bin/say', '-v', 'Samantha', '-r', '160', '--', '--file harmless text'])
        self.assertTrue(self.ui.revealed)

    def test_next_card_stops_previous_speech(self):
        self.words(3)
        self.enter()
        speech = self.spawn_speech.return_value
        speech.poll.return_value = None
        self.ui.reveal()
        self.ui.answer(False)
        speech.terminate.assert_called_once()
        self.assertFalse(self.ui.revealed)

    def test_repeated_click_restarts_audio_and_close_stops_it(self):
        self.words(1)
        self.enter()
        speech = self.spawn_speech.return_value
        speech.poll.return_value = None
        self.ui.reveal()
        self.ui.reveal()
        self.assertEqual(self.spawn_speech.call_count, 2)
        speech.terminate.assert_called_once()
        self.ui.close()
        self.assertEqual(speech.terminate.call_count, 2)
        self.ui.root.destroy.assert_called_once()

    def test_random_uses_custom_count(self):
        ids = self.words(32)
        self.ui.study_count.get.return_value = '25'
        self.ui.random_set()
        self.assertEqual(len(self.store.queue), 25)
        self.assertEqual(len(set(self.store.queue)), 25)
        self.assertTrue(set(self.store.queue).issubset(ids))

    def test_ordered_uses_oldest_first_and_skips_pending(self):
        ids = self.words(6)
        pending, _ = self.store.add('not yet translated')
        self.ui.study_count.get.return_value = '3'
        self.ui.ordered_set()
        self.assertEqual(self.store.queue, ids[:3])
        self.assertNotIn(pending, self.store.queue)

    def test_more_than_available_uses_all_ready_words(self):
        ids = self.words(4)
        self.ui.study_count.get.return_value = '100'
        self.ui.ordered_set()
        self.assertEqual(self.store.queue, ids)

    def test_invalid_count_keeps_current_progress(self):
        ids = self.words(3)
        self.store.start(ids)
        self.store.answer(True)
        before = (list(self.store.queue), self.store.total, self.store.done)
        with patch.object(app.messagebox, 'showinfo') as dialog:
            for value in ('0', '-1', '1.5', '', 'abc'):
                self.ui.study_count.get.return_value = value
                self.ui.random_set()
                self.ui.ordered_set()
                self.assertEqual((self.store.queue, self.store.total, self.store.done), before)
            self.assertEqual(dialog.call_count, 10)

    def test_tab_autostart_uses_custom_count(self):
        self.words(6)
        self.ui.study_count.get.return_value = '2'
        self.enter()
        self.assertEqual(len(self.store.queue), 2)


def gui_checks():
    """Run on a graphical desktop; all data is synthetic and temporary."""
    import tkinter as tk
    with tempfile.TemporaryDirectory() as directory:
        store = Store(directory)
        for i in range(9):
            store.add(f'word {i}', f'中文 {i}')
        root = tk.Tk()
        ui = app.App(root, store)
        try:
            for size in ('880x640', '1000x700', '1000x780'):
                root.geometry(size)
                root.update()
                for button in (ui.random_button, ui.ordered_button, ui.selected_button, ui.count_input):
                    assert button.winfo_ismapped(), (size, 'button unmapped')
                    assert button.winfo_height() >= button.winfo_reqheight(), (size, 'button clipped')
                    bottom = button.winfo_rooty() + button.winfo_height()
                    assert bottom <= root.winfo_rooty() + root.winfo_height(), (size, 'button below window')
                    assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width(), (size, 'button beyond right edge')
                print('PASS: start buttons visible at', size, flush=True)
            ui.tabs.select(ui.study)
            root.update()
            assert store.total == 9 and len(store.queue) == 9
            ui.english.event_generate('<Button-1>')
            root.update()
            assert ui.revealed and ui.chinese.cget('text').startswith('中文')
            ui.no.invoke()
            root.update()
            assert len(store.queue) == 9 and not ui.revealed
            ui.yes.invoke()
            root.update()
            assert store.done == 1 and len(store.queue) == 8
            for size in ('880x640', '1000x700', '1000x780'):
                root.geometry(size)
                root.update()
                for button in (ui.yes, ui.no):
                    assert button.winfo_ismapped()
                    assert button.winfo_rooty() + button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
            print('PASS: real tab, click, answer events and study button visibility', flush=True)
        finally:
            root.destroy()


if __name__ == '__main__':
    if '--gui' in sys.argv:
        gui_checks()
    else:
        unittest.main(verbosity=2)
