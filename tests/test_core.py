import concurrent.futures
import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Store
from collect import drain
from translate import translate, TranslationError, chunks

class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,*_):return json.dumps(self.data).encode()

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
        self.store=Store(self.path)
    def tearDown(self): self.tmp.cleanup()
    def test_translation_is_durable_and_duplicate_safe(self):
        i,created=self.store.add('  Hello  world '); self.assertTrue(created)
        j,created=Store(self.path).add('hello world'); self.assertFalse(created); self.assertEqual(i,j)
        drain(self.store,translator=lambda text:'你好，世界',notification=lambda _:None)
        s=Store(self.path); self.assertEqual(s.words[0]['zh'],'你好，世界'); self.assertEqual(s.words[0]['status'],'ready')
    def test_failure_keeps_english_and_retry(self):
        i,_=self.store.add('persistence')
        def fail(_): raise TranslationError('网络不可用')
        drain(self.store,translator=fail,notification=lambda _:None)
        self.store.reload(); w=self.store.words[0]
        self.assertEqual((w['en'],w['zh'],w['status']),('persistence','','error'))
        self.store.start([i]); self.assertEqual(self.store.queue,[])
        self.store.retry([i]); drain(self.store,translator=lambda _:'坚持',notification=lambda _:None)
        self.store.start([i]); self.assertEqual(self.store.queue,[i])
    def test_collect_while_studying(self):
        i,_=self.store.add('first','第一'); self.store.start([i])
        other=Store(self.path); j,_=other.add('second','第二')
        self.store.answer(True,expected=i)
        self.store.reload(); self.assertEqual(len(self.store.words),2)
        self.assertEqual((self.store.done,self.store.queue),(1,[]))
    def test_rotation_restore_and_completion(self):
        ids=[self.store.add(w,'释义')[0] for w in ['one','two','three']]
        self.store.start(ids); self.store.answer(False)
        self.assertEqual(self.store.queue,ids[1:]+ids[:1])
        s=Store(self.path); s.answer(True); s.answer(True); s.answer(True)
        self.assertEqual((s.queue,s.done,s.total),([],3,3))
    def test_concurrent_capture(self):
        def collect(i): return Store(self.path).add('Word '+str(i))
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            list(executor.map(collect,list(range(12))*2))
        self.store.reload(); self.assertEqual(len(self.store.words),12)
    def test_edit_or_delete_during_translation(self):
        i,_=self.store.add('edit'); job=self.store.claim()
        self.store.edit(i,'edit','手工释义'); self.store.finish(job,zh='过时译文')
        self.store.reload(); self.assertEqual(self.store.words[0]['zh'],'手工释义')
        j,_=self.store.add('delete'); job=self.store.claim(); self.store.delete([j]); self.store.finish(job,zh='删除')
        self.store.reload(); self.assertEqual(len(self.store.words),1)
    def test_legacy_import_once_preserves_file(self):
        p=self.path/'legacy'; p.mkdir()
        old={'words':[dict(id='a',en='test',zh='测试')],'queue':['a'],'done':0,'total':1}
        source=json.dumps(old); (p/'data.json').write_text(source)
        s=Store(p); self.assertEqual(s.queue,['a']); self.assertEqual(s.words[0]['zh'],'测试')
        s.delete(['a']); self.assertEqual(Store(p).words,[])
        self.assertEqual((p/'data.json').read_text(),source)
    def test_chunk_size(self):
        for text in ['long word '*300,'a'*1200,'英文é'*400]:
            parts=chunks(text)
            self.assertTrue(all(len(s.encode())<=450 for s in parts))
            self.assertEqual(''.join(''.join(parts).split()),''.join(text.split()))
    def test_api_parsing_and_errors(self):
        def ok(req,timeout):
            self.assertTrue(req.full_url.startswith('https://api.mymemory.translated.net/get?'))
            return Response({'responseStatus':200,'responseData':{'translatedText':'你好 &amp; 再见'}})
        self.assertEqual(translate('Hello and goodbye',opener=ok),'你好 & 再见')
        for data in [{'responseStatus':403,'responseDetails':'LIMIT EXCEEDED'}, {'responseStatus':200,'responseData':{'translatedText':'hello'}},[]]:
            with self.assertRaises(TranslationError):translate('hello',opener=lambda *a,**k:Response(data))
    def test_interrupted_worker_and_bad_input(self):
        self.store.add('recover'); self.store.claim()
        drain(self.store,translator=lambda _:'恢复',notification=lambda _:None)
        self.store.reload(); self.assertEqual(self.store.words[0]['status'],'ready')
        for text in ['', 'x'*1201]:
            with self.assertRaises(ValueError):self.store.add(text)

if __name__=='__main__':unittest.main(verbosity=2)
