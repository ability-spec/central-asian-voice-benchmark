"""Bound memory while preserving active conversation history."""
from concurrent.futures import ThreadPoolExecutor

from product.backend.services import session


def test_unknown_reads_do_not_create_sessions():
    manager = session.SessionManager(max_sessions=2)
    for i in range(100):
        assert manager.get_history(str(i)) == []
        assert manager.get_turn_count(str(i)) == 0
        assert manager.session_age(str(i)) == 0
    assert not manager._sessions and not manager._created and not manager._last_used


def test_capacity_evicts_least_recently_used_session():
    manager = session.SessionManager(max_sessions=2)
    manager.add_turn('a', 'user', 'first')
    manager.add_turn('b', 'user', 'second')
    manager.get_history('a')
    manager.add_turn('c', 'user', 'third')
    assert manager.get_history('b') == []
    assert manager.get_turn_count('a') == manager.get_turn_count('c') == 1
    assert len(manager._sessions) == len(manager._created) == len(manager._last_used) == 2


def test_idle_expiration_preserves_recently_used_history(monkeypatch):
    clock = [0]
    monkeypatch.setattr(session.time, 'monotonic', lambda: clock[0])
    manager = session.SessionManager(idle_timeout_seconds=10)
    manager.add_turn('old', 'user', 'first')
    manager.add_turn('active', 'user', 'second')
    clock[0] = 8
    manager.get_history('active')
    clock[0] = 11
    assert manager.get_history('old') == []
    assert manager.get_history('active')[0]['content'] == 'second'
    assert manager.session_age('active') == 11
    assert 'old' not in manager._created and 'old' not in manager._last_used


def test_history_is_a_detached_snapshot():
    manager = session.SessionManager()
    manager.add_turn('a', 'user', 'original')
    manager.get_history('a')[0]['content'] = 'changed'
    assert manager.get_history('a')[0]['content'] == 'original'


def test_parallel_worker_appends_are_not_lost():
    manager = session.SessionManager()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: manager.add_turn('a', 'user', str(i)), range(100)))
    assert manager.get_turn_count('a') == 100
    assert {item['content'] for item in manager.get_history('a')} == {str(i) for i in range(100)}
