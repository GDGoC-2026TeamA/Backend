import os

import psycopg
from psycopg.rows import dict_row


def db():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        yield conn
