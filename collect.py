"""macOS Service entry point; selected text is received on stdin, never evaluated."""
import fcntl
import subprocess
import sys
from pathlib import Path
from core import Store, DATA_DIR
from translate import translate, TranslationError

def notify(message):
    # A fixed script plus argv avoids interpreting collected content as code.
    script='on run argv\n display notification (item 1 of argv) with title "英语卡片"\nend run'
    try:
        subprocess.run(['/usr/bin/osascript','-e',script,message], stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
    except (OSError,subprocess.TimeoutExpired): pass

def launch_worker():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    with open(DATA_DIR/'worker.log','a') as log:
        return subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)

def drain(store, translator=translate, notification=notify):
    with open(store.directory/'translation.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        store.recover_interrupted()
        while (job:=store.claim()) is not None:
            try:
                zh=translator(job['en'])
                store.finish(job,zh=zh)
                notification('已收藏英文和中文释义。')
            except TranslationError as e:
                store.finish(job,error=str(e))
                notification('英文已收藏，翻译未完成。请在程序中查看并重试。')
            except Exception:
                store.finish(job,error='翻译发生异常，英文已保留，请重试。')

def main():
    store=Store()
    if '--worker' in sys.argv:
        drain(store); return
    # Bound input size without truncating silently.
    text=sys.stdin.read(10000)
    word_id,created=store.add(text)
    if not created:
        store.retry([word_id])
        notify('这条英文已在收藏中。')
    launch_worker()

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(str(e),file=sys.stderr)
        sys.exit(1)
