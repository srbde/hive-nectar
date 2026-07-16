import logging
from collections.abc import Callable
from queue import Queue
from threading import Event, Thread
from time import sleep
from typing import Any

log = logging.getLogger(__name__)

FUTURES_MODULE = None
try:
    from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: F401

    FUTURES_MODULE = "futures"
except ImportError:
    FUTURES_MODULE = None


def default_handler(name: str, exception: Exception, *args: Any, **kwargs: Any) -> None:
    log.warning(f"{name} raised {exception} with args {args!r} and kwargs {kwargs!r}")
    pass


class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""

    def __init__(
        self,
        name: str,
        queue: Queue,
        results: Queue,
        abort: Event,
        idle: Event,
        exception_handler: Callable,
    ) -> None:
        Thread.__init__(self)
        self.name = name
        self.queue = queue
        self.results = results
        self.abort = abort
        self.idle = idle
        self.exception_handler = exception_handler
        self.daemon = True
        self.start()

    def run(self) -> None:
        """Thread work loop calling the function with the params"""
        # keep running until told to abort
        while not self.abort.is_set():
            try:
                # get a task and raise immediately if none available
                func, args, kwargs = self.queue.get(False)
                self.idle.clear()
            except Exception:
                # no work to do
                # if not self.idle.is_set():
                #  print >> stdout, '%s is idle' % self.name
                self.idle.set()
                # time.sleep(1)
                continue

            try:
                # the function may raise
                result = func(*args, **kwargs)
                # print(result)
                if result is not None:
                    self.results.put(result)
            except Exception as e:
                # so we move on and handle it in whatever way the caller wanted
                self.exception_handler(self.name, e, args, kwargs)
            finally:
                # task complete no matter what happened
                self.queue.task_done()


# class for thread pool
class Pool:
    """Pool of threads consuming tasks from a queue"""

    def __init__(
        self,
        thread_count: int,
        batch_mode: bool = True,
        exception_handler: Callable = default_handler,
    ) -> None:
        # batch mode means block when adding tasks if no threads available to process
        self.queue = Queue(thread_count if batch_mode else 0)
        self.resultQueue = Queue(0)
        self.thread_count = thread_count
        self.exception_handler = exception_handler
        self.aborts = []
        self.idles = []
        self.threads = []

    def __del__(self) -> None:
        """Tell my threads to quit"""
        self.abort()

    def run(self, block: bool = False) -> bool:
        """Start the threads, or restart them if you've aborted"""
        # either wait for them to finish or return false if some arent
        if block:
            while self.alive():
                sleep(1)
        elif self.alive():
            return False

        # go start them
        self.aborts = []
        self.idles = []
        self.threads = []
        for n in range(self.thread_count):
            abort = Event()
            idle = Event()
            self.aborts.append(abort)
            self.idles.append(idle)
            self.threads.append(
                Worker(
                    "thread-%d" % n,
                    self.queue,
                    self.resultQueue,
                    abort,
                    idle,
                    self.exception_handler,
                )
            )
        return True

    def enqueue(self, func: Callable, *args: Any, **kargs: Any) -> None:
        """Add a task to the queue"""
        self.queue.put((func, args, kargs))

    def join(self) -> None:
        """Wait for completion of all the tasks in the queue"""
        self.queue.join()

    def abort(self, block: bool = False) -> None:
        """Tell each worker that its done working"""
        # tell the threads to stop after they are done with what they are currently doing
        for a in self.aborts:
            a.set()
        # wait for them to finish if requested
        while block and self.alive():
            sleep(1)

    def alive(self) -> bool:
        """Returns True if any threads are currently running"""
        return True in [t.is_alive() for t in self.threads]

    def idle(self) -> bool:
        """Returns True if all threads are waiting for work"""
        return False not in [i.is_set() for i in self.idles]

    def done(self) -> bool:
        """Returns True if not tasks are left to be completed"""
        return self.queue.empty()

    def results(self, sleep_time: int | float = 0) -> list[Any]:
        """Get the set of results that have been processed, repeatedly call until done"""
        sleep(sleep_time)
        results = []
        try:
            while True:
                # get a result, raises empty exception immediately if none available
                results.append(self.resultQueue.get(False))
                self.resultQueue.task_done()
        except Exception:
            return results
        return results
