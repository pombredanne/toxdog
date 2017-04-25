""" Automatically run tox jobs for real-time feedback on changes. """

# Copyright 2017 Seth Michael Larson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = 'Seth Michael Larson'
__email__ = 'sethmichaellarson@protonmail.com'
__license__ = 'Apache-2.0'
__version__ = '1.0.0'

import argparse
import multiprocessing
import os
import sys
try:
    import subprocess32 as subprocess
except ImportError:
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
    def __init__(self, env, path):
        self.env = env
        self.proc = subprocess.Popen('tox -e %s' % env,
                                     shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,
                                     cwd=path)
        self.output = b''
        self._buffer = b''

    @property
    def exit_status(self):
        return self.proc.returncode

    def poll(self):
        start_value = self.proc.returncode
        try:
            self.proc.poll()
        except Exception:
            return False
        return self.proc.returncode is not start_value

    def terminate(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None


class ToxdogThread(threading.Thread):
    def __init__(self, queue, path, envs, omit_envs):
        super(ToxdogThread, self).__init__()
        self.queue = queue
        self.path = path
        self.envs = envs
        self.omit_envs = omit_envs
        self.running = True
        self.tox_procs = {}
        self.tox_waiting_envs = []
        self.lock = threading.Lock()
        self.reason = ''
        self.max_concurrent = min(4, multiprocessing.cpu_count())

    def run(self):
        while self.running:
            try:
                event = self.queue.get_nowait()
                if event is None:
                    self.start_processes(Fore.LIGHTCYAN_EX + 'INITIAL' + Fore.LIGHTWHITE_EX)
                else:
                    assert isinstance(event, FileSystemEvent)
                    path = os.path.relpath(event.src_path, self.path)
                    if event.event_type == EVENT_TYPE_DELETED:
                        action = 'DELETE'
                    else:
                        action = 'MODIFY'
                    action = Fore.LIGHTCYAN_EX + action + Fore.LIGHTWHITE_EX
                    self.start_processes('%s %s' % (action, path))
            except Empty:
                self.poll_processes()
                time.sleep(0.5)

        self.kill_processes()

    def start_processes(self, reason):
        self.reason = reason
        try:
            tox_config = parseconfig(['-c', self.path])
        except Exception:
            return

        self.kill_processes()

        self.tox_waiting_envs = [x for x in sorted(tox_config.envconfigs) if (len(self.envs) == 0 or x in self.envs) and x not in self.omit_envs]
        for env in self.tox_waiting_envs:
            self.tox_procs[env] = None
        self.start_next_process()

        self.update_status()

    def start_next_process(self):
        if len(self.tox_waiting_envs) > 0:
            tox_env = self.tox_waiting_envs[0]
            self.tox_waiting_envs = self.tox_waiting_envs[1:]
            self.tox_procs[tox_env] = ToxProcess(tox_env, self.path)
            if self._running_processes() < self.max_concurrent:
                self.start_next_process()
            else:
                self.update_status()

    def poll_processes(self):
        for env, proc in sorted(self.tox_procs.items()):
            if proc is not None and proc.exit_status is None:
                proc.poll()
                if proc.exit_status is not None and self._running_processes() < self.max_concurrent:
                    self.start_next_process()
        self.update_status()

    def kill_processes(self):
        for _, proc in self.tox_procs.items():
            if proc is not None:
                proc.terminate()
        self.tox_procs = {}

    def _running_processes(self):
        running = 0
        for _, proc in self.tox_procs.items():
            if proc is not None and proc.exit_status is None:
                running += 1
        return running

    def update_status(self):
        with self.lock:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

            for env, proc in sorted(self.tox_procs.items()):
                if proc is None:
                    sys.stdout.write(Fore.LIGHTBLACK_EX + env + Style.RESET_ALL + ' ')
                elif proc.exit_status is None:
                    sys.stdout.write(Fore.LIGHTYELLOW_EX + env + Style.RESET_ALL + ' ')
                elif proc.exit_status == 0:
                    sys.stdout.write(Fore.LIGHTGREEN_EX + env + Style.RESET_ALL + ' ')
                else:
                    sys.stdout.write(Fore.LIGHTRED_EX + env + Style.RESET_ALL + ' ')

            sys.stdout.write(Fore.LIGHTWHITE_EX + self.reason + Style.RESET_ALL)
            sys.stdout.flush()


class ToxdogEventHandler(RegexMatchingEventHandler):
    def __init__(self, path, envs, omit_envs, max_concurrent):
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

        self.thread = ToxdogThread(self.queue, path, envs, omit_envs)
        self.thread.max_concurrent = max_concurrent

    def start(self):
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
    parser = argparse.ArgumentParser()
    parser.add_argument('-c',
                        nargs='?',
                        default=os.getcwd(),
                        help=('Location of the tox.ini file. Defaults to '
                              'current working directory.'))
    parser.add_argument('-n',
                        nargs='?',
                        default=min(8, multiprocessing.cpu_count()),
                        help=('Number of concurrent jobs allowed. Default '
                              'is number of CPUs or 8, whichever is smaller.'))
    parser.add_argument('-e',
                        nargs='*',
                        help=('Environments to allow from the tox.ini file. '
                              'Default is all environments.'))
    parser.add_argument('-o',
                        nargs='*',
                        help=('Environments to omit from the tox.ini file. '
                              'Default is omitting no environments.'))

    args = vars(parser.parse_args(sys.argv[1:]))

    observer = Observer()
    handler = ToxdogEventHandler(args['c'], args['e'] or [], args['o'] or [], int(args['n']))
    handler.start()
    observer.schedule(handler, args['c'], True)
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
