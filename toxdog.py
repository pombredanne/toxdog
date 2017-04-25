__author__ = 'Seth Michael Larson'
__email__ = 'sethmichaellarson@protonmail.com'
__license__ = 'MIT'
__version__ = 'dev'

import os
import sys
import subprocess
import time
import threading
from colorama import init, Fore, Style
from tox.config import parseconfig
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import (RegexMatchingEventHandler, FileSystemEvent, EVENT_TYPE_DELETED)

init()

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

DEVNULL = open(os.devnull, 'a+')


class ToxProcess(object):
    def __init__(self, env):
        self.env = env
        self.proc = subprocess.Popen('tox -e %s' % env,
                                     shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,
                                     cwd=os.getcwd())
        self.output = b''
        self._buffer = b''

    @property
    def exit_status(self):
        return self.proc.returncode

    def poll(self):
        start_value = self.proc.returncode
        try:
            self.proc.communicate(timeout=0.1)
        except subprocess.TimeoutExpired:
            return False
        return self.proc.returncode is not start_value

    def terminate(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None


class ToxdogThread(threading.Thread):
    def __init__(self, queue):
        super(ToxdogThread, self).__init__()
        self.queue = queue
        self.running = True
        self.tox_procs = {}
        self.lock = threading.Lock()
        self.reason = ''

    def run(self):
        while self.running:
            try:
                event = self.queue.get_nowait()
                if event is None:
                    self.start_processes(Fore.LIGHTCYAN_EX + 'INITIAL' + Fore.LIGHTWHITE_EX)
                else:
                    assert isinstance(event, FileSystemEvent)
                    path = os.path.relpath(event.src_path, os.getcwd())
                    if event.event_type == EVENT_TYPE_DELETED:
                        action = 'DELETE'
                    else:
                        action = 'MODIFY'
                    action = Fore.LIGHTCYAN_EX + action + Fore.LIGHTWHITE_EX
                    self.start_processes('%s %s' % (action, path))
            except Empty:
                self.poll_processes()
                time.sleep(1.0)

        self.kill_processes()

    def start_processes(self, reason):
        self.reason = reason
        try:
            tox_config = parseconfig()
        except Exception:
            return

        self.kill_processes()

        for env in sorted(tox_config.envconfigs):
            self.tox_procs[env] = ToxProcess(env)

        self.update_status()

    def poll_processes(self):
        for env, proc in sorted(self.tox_procs.items()):
            if proc.exit_status is None:
                proc.poll()
        self.update_status()

    def kill_processes(self):
        for _, proc in self.tox_procs.items():
            proc.terminate()
        self.tox_procs = {}

    def update_status(self):
        with self.lock:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

            for env, proc in sorted(self.tox_procs.items()):
                if proc.exit_status is None:
                    sys.stdout.write(Fore.LIGHTYELLOW_EX + env + Style.RESET_ALL + ' ')
                elif proc.exit_status == 0:
                    sys.stdout.write(Fore.LIGHTGREEN_EX + env + Style.RESET_ALL + ' ')
                else:
                    sys.stdout.write(Fore.LIGHTRED_EX + env + Style.RESET_ALL + ' ')

            sys.stdout.write(Fore.LIGHTWHITE_EX + self.reason + Style.RESET_ALL)
            sys.stdout.flush()


class ToxdogEventHandler(RegexMatchingEventHandler):
    def __init__(self):
        super(ToxdogEventHandler, self).__init__(regexes=['.*\.py$', '.*\.rst$', '.*\.md$', '.*/tox\.ini$'],
                                                 ignore_directories=True,
                                                 ignore_regexes=['.*/__pycache__/.*',
                                                                 '\.ropeproject/.*',
                                                                 '.*\$py\.class$',
                                                                 '.*/\.Python/.*',
                                                                 '.*/env/.*',
                                                                 '.*/builds/.*',
                                                                 '.*/develop-eggs/.*',
                                                                 '.*/dist/.*',
                                                                 '.*/downloads/.*',
                                                                 '.*/eggs/.*',
                                                                 '.*/\.eggs/.*',
                                                                 '.*/lib/.*',
                                                                 '.*/lib64/.*',
                                                                 '.*/\.egg-info/.*',
                                                                 '.*/\.tox/.*'])
        self.queue = Queue()
        self.last_event = 0

        self.thread = None

    def start(self):
        self.thread = ToxdogThread(self.queue)
        self.thread.start()
        self.queue.put_nowait(None)

    def stop(self):
        self.thread.running = False
        self.thread.join()

    def handle_event(self, event):
        current_time = time.time()
        if current_time - self.last_event < 1.0:
            return
        self.queue.put(event)

    def on_deleted(self, event):
        self.handle_event(event)

    def on_modified(self, event):
        self.handle_event(event)


def main():
    observer = Observer()
    handler = ToxdogEventHandler()
    handler.start()
    observer.schedule(handler, os.getcwd(), True)
    observer.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        observer.stop()
        handler.stop()

    sys.stdout.write("\r\033[K")
    sys.stdout.flush()

    observer.join()


if __name__ == '__main__':
    main()
