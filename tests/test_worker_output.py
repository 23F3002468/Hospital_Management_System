"""Console output of the worker and the setup scripts.

Regression cover for #15. Python picks the console codec for stdout, which is
cp1252 on a stock Windows terminal - it has no place for an emoji, so a single
one in a ``print`` raised ``UnicodeEncodeError`` and took the task (or the
whole script) down.

These read the source rather than importing it: ``celery_worker`` calls
``create_app()`` at import time, which would build a second Flask app pointed at
the real ``hospital.db``.
"""

import pathlib

import pytest

CONSOLE_SCRIPTS = ['init_db.py', 'test_email.py']


def source(app, name):
    return (pathlib.Path(app.root_path) / name).read_text(encoding='utf-8')


@pytest.mark.parametrize('name', CONSOLE_SCRIPTS)
def test_console_scripts_are_ascii_only(app, name):
    """These print directly, so nothing in them may leave the cp1252 range."""
    try:
        source(app, name).encode('cp1252')
    except UnicodeEncodeError as exc:
        pytest.fail(f'{name} contains a character no Windows console can print: {exc}')


def test_the_worker_logs_rather_than_prints(app):
    """print() has no task id, no level, and writes through the console codec.

    Parsed rather than grepped - the module's own comments mention ``print()``.
    """
    import ast

    tree = ast.parse(source(app, 'celery_worker.py'))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == 'print')
            or (isinstance(node.func, ast.Attribute) and node.func.attr == 'print_exc')
        )
    ]
    assert not calls, f'celery_worker.py still writes to stdout at lines ' \
                      f'{[node.lineno for node in calls]}'
    assert 'get_task_logger' in source(app, 'celery_worker.py')


def test_the_only_non_ascii_left_in_the_worker_is_email_content(app):
    """The reminder body and subject keep their emoji - mail is UTF-8, not cp1252.

    Everything else must be printable on a Windows console. If this fails, an
    emoji has crept back into a log line.
    """
    non_ascii_lines = [
        line.strip() for line in source(app, 'celery_worker.py').splitlines()
        if any(ord(char) > 127 for char in line)
    ]
    for line in non_ascii_lines:
        assert 'logger' not in line, f'non-ascii reached a log call: {line}'
