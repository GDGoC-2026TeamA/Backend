import os
from collections.abc import Iterator

import psycopg
from psycopg.rows import DictRow, dict_row


def db() -> Iterator[psycopg.Connection[DictRow]]:
    # psycopg.connect는 Connection[TupleRow]로 추론되므로 행 타입을 명시한다.
    with psycopg.Connection[DictRow].connect(
        os.environ["DATABASE_URL"], row_factory=dict_row
    ) as conn:
        yield conn
