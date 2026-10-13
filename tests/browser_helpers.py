import time


def wait_for_async(page, predicate, arg=None, timeout=10000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if page.evaluate(predicate, arg):
            return
        page.wait_for_timeout(25)
    raise AssertionError('Asynchronous browser condition did not become true')
