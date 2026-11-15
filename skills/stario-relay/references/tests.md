# Tests for a Relay page

Each stream sends its own `tab` in the signals of the GET. Read the first event before the
command, so the subscription is up.

```python
# tests/test_notes.py
from app.urls import ADD_NOTE, NOTES_LIVE, RENAME_NOTE

TAB, OTHER = {"datastar": '{"tab": "t1"}'}, {"datastar": '{"tab": "t2"}'}


async def test_rename_repaints_every_tab(client):
    await client.post(ADD_NOTE.href(), json={"title": "milk"})
    async with (
        client.stream("GET", NOTES_LIVE.href(), params=TAB, timeout=2) as mine,
        client.stream("GET", NOTES_LIVE.href(), params=OTHER, timeout=2) as other,
    ):
        one, two = mine.iter_events(), other.iter_events()
        await anext(one)
        await anext(two)
        r = await client.post(RENAME_NOTE.href(), json={"editing_id": 1, "new_title": "eggs"})
        assert r.status_code == 204
        assert "eggs" in (await anext(one))["data"]
        assert "eggs" in (await anext(two))["data"]


async def test_a_duplicate_answers_its_own_tab(client):
    await client.post(ADD_NOTE.href(), json={"title": "milk"})
    r = await client.post(ADD_NOTE.href(), json={"title": "Milk"})
    assert "already on the list" in r.text


async def test_bad_ids_are_refused(client):
    for bad in ({"editing_id": 9, "new_title": "x"}, {"editing_id": True, "new_title": "x"}):
        assert (await client.post(RENAME_NOTE.href(), json=bad)).status_code == 404
    assert (
        await client.get(NOTES_LIVE.href(), params={"datastar": '{"tab": "a b"}'})
    ).status_code == 400
```

A message to one tab arrives on that tab's stream as `event["event"] == "datastar-patch-signals"`; the other stream gets nothing.
