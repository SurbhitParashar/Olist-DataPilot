import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger('olist-analytics')


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


@contextmanager
def timed_span(name: str, **fields) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info('span=%s elapsed_ms=%.1f fields=%s', name, elapsed_ms, fields)
