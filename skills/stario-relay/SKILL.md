---
name: stario-relay
description: A live Stario page on state in memory (Relay), a message to one tab, an edit dialog that keeps what the user typed. Use when state is in memory, or any page needs an edit dialog or a message to one tab.
---

# Relay: state in memory, and messages to one tab

One `Relay[dict]` per app, built in `bootstrap`, shared by every page. Two kinds of subject:

- `notes.changed` carries `{}`. Each command publishes it after it changes the state; each stream renders again.
- `tab.<id>` carries signals for one browser tab, named by its tab id. Only the stream of that tab sends them.

```text
relay: Relay[dict] = Relay()            # in bootstrap
relay.publish("notes.changed", {})      # dotted subject
async with relay.subscribe("notes.changed", "tab.t1", latest=True) as events:  # also "notes.*"
    async for subject, payload in c.alive(events): ...
```

## A live page in memory

Notes that several people rename at once; the edit dialog survives each repaint.

```python
# app/data.py
from dataclasses import dataclass, field
from itertools import count


@dataclass(slots=True)
class Note:
    id: int
    title: str


@dataclass(slots=True)
class Notes:
    rows: dict[int, Note] = field(default_factory=dict)
    ids: count[int] = field(default_factory=lambda: count(1))


def list_notes(notes: Notes) -> list[Note]:
    return sorted(notes.rows.values(), key=lambda n: n.id)


def add_note(notes: Notes, title: str) -> Note:
    note = Note(next(notes.ids), title)
    notes.rows[note.id] = note
    return note
```

```python
# app/urls.py
NOTES = Route("GET /notes")
NOTES_LIVE = Route("GET /notes/live")
ADD_NOTE = Route("POST /notes")
RENAME_NOTE = Route("POST /notes/rename")
```

```python
# app/pages/notes.py
import uuid
from dataclasses import dataclass

from stario import App, Context, Relay, Writer, h
from stario.datastar import SSE, at, data, read_signals
from stario.datastar.format import string_literal
from stario.markup import HtmlElement

from app.data import Note, Notes, add_note, list_notes
from app.layout import page
from app.urls import ADD_NOTE, NOTES, NOTES_LIVE, RENAME_NOTE

CHANGED = "notes.changed"


@dataclass(frozen=True, slots=True)
class NotesPage:
    notes: Notes
    relay: Relay[dict]

    def register(self, app: App) -> None:
        app.add(NOTES, self.show)
        app.add(NOTES_LIVE, self.live)
        app.add(ADD_NOTE, self.add)
        app.add(RENAME_NOTE, self.rename)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(list_notes(self.notes), uuid.uuid7().hex))

    async def live(self, c: Context, w: Writer) -> None:
        tab = str((await read_signals(c.req)).get("tab", ""))
        if not (tab.isalnum() and len(tab) <= 32):
            w.text("tab must be a short id", status=400)
            return
        async with self.relay.subscribe(CHANGED, f"tab.{tab}", latest=True) as events:
            sse = SSE(w)
            sse.patch_elements(render(list_notes(self.notes), tab))
            async for subject, signals in c.alive(events):
                if subject == CHANGED:
                    sse.patch_elements(render(list_notes(self.notes), tab))
                else:
                    sse.patch_signals(signals)

    async def add(self, c: Context, w: Writer) -> None:
        title = str((await read_signals(c.req)).get("title", "")).strip()
        if not 1 <= len(title) <= 200:
            SSE(w).patch_signals({"_error": "title must be 1 to 200 characters"})
            return
        if any(n.title.lower() == title.lower() for n in list_notes(self.notes)):
            SSE(w).patch_signals({"_error": f"“{title}” is already on the list."})
            return
        add_note(self.notes, title)
        self.relay.publish(CHANGED, {})
        SSE(w).patch_signals({"title": "", "_error": ""})

    async def rename(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        note_id = signals.get("editing_id")
        title = str(signals.get("new_title", "")).strip()
        if type(note_id) is not int or (note := self.notes.rows.get(note_id)) is None:
            w.text("no such note", status=404)
            return
        if not 1 <= len(title) <= 200:
            SSE(w).patch_signals({"_error": "title must be 1 to 200 characters"})
            return
        note.title = title
        self.relay.publish(CHANGED, {})
        w.empty()


def render(notes: list[Note], tab: str) -> HtmlElement:
    return page(
        "Notes",
        h.Main(
            {"id": "notes"},
            data.signals(
                {"tab": tab, "title": "", "editing_id": 0, "new_title": "", "_error": ""},
                if_missing=True,
            ),
            data.init(at.get(NOTES_LIVE.href(), retry="always")),
            h.Form(
                data.on("submit", at.post(ADD_NOTE.href()), prevent=True),
                h.Input({"type": "text", "maxlength": 200}, data.bind("title")),
                h.Button({"type": "submit"}, "Add"),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
            ),
            h.Ul(*[item(n) for n in notes]),
            h.Dialog(
                data.ref("_edit"),
                data.preserve_attr("open"),
                h.Form(
                    data.on(
                        "submit", at.post(RENAME_NOTE.href()) + "; $_edit.close()", prevent=True
                    ),
                    h.Input({"type": "text", "required": True}, data.bind("new_title")),
                    h.Button({"type": "submit"}, "Save"),
                ),
            ),
        ),
    )


def item(n: Note) -> HtmlElement:
    edit = f"$editing_id = {n.id}; $new_title = {string_literal(n.title)}; $_edit.showModal()"
    return h.Li(n.title, h.Button({"type": "button"}, data.on("click", edit), "Rename"))
```

In `bootstrap`: `relay: Relay[dict] = Relay()`, then `NotesPage(Notes(), relay).register(app)`.

- The page `GET` makes a new `tab`, and the stream renders the same `tab`, so the `data-signals` text stays the same in every render.
- Subscribe before the first render, so no change falls between them.
- `data.ref("_edit")` puts the dialog in `$_edit`; `preserve_attr("open")` keeps it open through a repaint; `if_missing=True` keeps what the user typed. The server never renders the dialog open.
- `type(...) is not int` also rejects `true`, which `isinstance` accepts.

## A message to one tab

Work that ends after the reply (a job, skill `stario-jobs`) answers its tab through the stream: the command reads `tab` from the signals and validates it like the stream does, and the work publishes `self.relay.publish(f"tab.{tab}", {"_toast": "Saved."})`. Send every changed signal in one publish; `latest=True` keeps only the newest message per subject. The scaffold's `page()` already renders `_toast` and clears it after 4 seconds.

Rows in SQLite plus a tab message: the stream subscribes to `tab.<id>` and reads the rows again on `CHANGED`; each command awaits its write, then publishes. Tests for this page: `references/tests.md`.
