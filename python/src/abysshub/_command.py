"""The ``abysshub`` command. ``abysshub publish <folder>`` does what a person does on the
website's Publish page, through `/v1`'s routes that change a Widget; ``abysshub status``
shows the Widget on Abyss beside the folder, and ``abysshub pull`` takes its listing. It
asks nothing at a prompt: it stops or it goes, and every stop exits non-zero with its ``code``."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ._client import Abyss, _expect, _has_ended, _is_key, _is_upload, _is_widget
from ._error import AbyssError
from ._files import file
from ._run import _downloaded
from ._types import parse_upload

PUBLISH_FILE = "abyss.json"
TEST_INPUTS = "test_inputs.json"
INTERFACE = "interface.json"
ROOT_ENV = (".env", ".env.*")
"""A root ``.env`` and its variants: never content, whatever the Junk list says."""
LISTING_FIELDS = ("title", "description", "tags", "visibility", "price", "free_runs")
"""The Listing Fields the Publish File holds, beside its thumbnail."""
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
"""The extensions a thumbnail may have: an image's."""
JSON = {"Content-Type": "application/json"}
SOURCES = {"widget": "the Widget", "account": "your account"}
"""Where an Environment name comes from, in words."""


def main(argv: list[str] | None = None) -> int:
    """Runs the command and answers its exit code."""
    parser = argparse.ArgumentParser(prog="abysshub", description="Publish a Widget folder to Abyss.")
    verbs = parser.add_subparsers(dest="verb", metavar="<verb>")
    verbs.required = True
    publish_verb = verbs.add_parser(
        "publish",
        help="publish a Widget folder and print its link",
        description=f"Publish a Widget folder, with its {PUBLISH_FILE} and {TEST_INPUTS}, and print its link.",
    )
    publish_verb.add_argument("folder", type=Path)
    publish_verb.add_argument(
        "--force", action="store_true", help="publish over a Widget that moved on Abyss: the folder wins"
    )
    status_verb = verbs.add_parser(
        "status",
        help="show the Widget on Abyss beside the folder, changing nothing",
        description="Show the Widget on Abyss beside the folder: its link, its version, each Listing Field that "
        "differs, where each Environment name comes from, and whether it moved. Changes nothing.",
    )
    status_verb.add_argument("folder", type=Path)
    pull_verb = verbs.add_parser(
        "pull",
        help="take the Widget's listing and thumbnail from Abyss into the folder",
        description=f"Write the Widget's Listing Fields into {PUBLISH_FILE} and its thumbnail into the folder. "
        "Never touches code.",
    )
    pull_verb.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    if args.verb == "publish":
        widget_folder, faults = _read_folder(args.folder)
    else:
        publish_file, faults = _read_publish_file(args.folder)
        if faults:
            return _stop(faults)
        if args.verb == "status" and "version" not in (publish_file.get("widget") or {}):
            print(f"{args.folder} was never published: `abysshub publish {args.folder}` publishes it.")
            return 0
    try:
        abyss = Abyss()
    except AbyssError as error:
        return _stop([*faults, (error.code, error.message)])
    with abyss:
        try:
            if args.verb == "publish":
                faults.extend(_key_faults(abyss))
                if faults:
                    return _stop(faults)
                print(publish(abyss, args.folder, widget_folder, args.force))
            elif args.verb == "status":
                status(abyss, args.folder, publish_file)
            else:
                pull(abyss, args.folder, publish_file)
        except AbyssError as error:
            print(f"abysshub: stopped: {error.code}: {error.message}", file=sys.stderr)
            if error.request_id:
                print(f"request_id: {error.request_id}", file=sys.stderr)
            return 1
        except OSError as error:
            # A file the folder names changed or became unreadable after the check.
            print(f"abysshub: stopped: file_unreadable: {error}", file=sys.stderr)
            return 1
    return 0


@dataclass
class _Folder:
    """A Widget folder as the command read it, before it sent anything."""

    publish_file: dict[str, Any]
    interface: list[Any] | None
    test_input: dict[str, Any]
    """The Test Run's input: the Test Inputs, and the default of each Field they leave out."""


def _stop(faults: list[tuple[str, str]]) -> int:
    """Prints every fault, one line each with its code, and answers the exit code."""
    for code, message in faults:
        print(f"abysshub: stopped: {code}: {message}", file=sys.stderr)
    return 1


def _read_folder(folder: Path) -> tuple[_Folder, list[tuple[str, str]]]:
    """Reads the folder and finds every fault it shows on its own, all of them and not
    only the first, without a request: a publish takes minutes, a fault stops it now."""
    faults: list[tuple[str, str]] = []
    for name, code in (("run.py", "run_py_missing"), ("requirements.txt", "requirements_missing")):
        if not (folder / name).is_file():
            faults.append((code, f"The folder has no {name}."))
    publish_file = _read_json(folder / PUBLISH_FILE, "publish_file", dict, faults)
    if publish_file is not None:
        _check_listing(folder, publish_file, faults)
    has_interface = (folder / INTERFACE).is_file()
    interface = _read_json(folder / INTERFACE, "interface", list, faults) if has_interface else None
    test_inputs = _read_json(folder / TEST_INPUTS, "test_inputs", dict, faults) if (folder / TEST_INPUTS).is_file() else {}
    test_input: dict[str, Any] = {}
    # An invalid interface.json skips the Field checks rather than calling every Test Input unknown.
    if test_inputs is not None and (interface is not None or not has_interface):
        test_input = _check_test_inputs(folder, interface or [], test_inputs, faults)
    return _Folder(publish_file or {}, interface, test_input), faults


def _read_publish_file(folder: Path) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Reads the Publish File alone, as ``status`` and ``pull`` need it, with its faults."""
    faults: list[tuple[str, str]] = []
    publish_file = _read_json(folder / PUBLISH_FILE, "publish_file", dict, faults)
    if publish_file is not None and not isinstance(publish_file.get("widget") or {}, dict):
        faults.append(("publish_file_invalid", f"The widget block of {PUBLISH_FILE} is not a JSON object."))
    return publish_file or {}, faults


def _check_listing(folder: Path, publish_file: dict[str, Any], faults: list[tuple[str, str]]) -> None:
    """The Publish File's faults: no title, no tag, and a thumbnail that is missing on a
    first publish or names no image file in the folder."""
    block = publish_file.get("widget") or {}
    if not isinstance(block, dict):
        faults.append(("publish_file_invalid", f"The widget block of {PUBLISH_FILE} is not a JSON object."))
    title = publish_file.get("title")
    if not isinstance(title, str) or not title.strip():
        faults.append(("title_missing", f"{PUBLISH_FILE} has no title."))
    tags = publish_file.get("tags")
    if not isinstance(tags, list) or not any(isinstance(tag, str) and tag.strip() for tag in tags):
        faults.append(("tag_missing", f"{PUBLISH_FILE} has no tag in tags."))
    thumbnail = publish_file.get("thumbnail")
    if not thumbnail:
        if not (isinstance(block, dict) and "version" in block):
            faults.append(("thumbnail_missing", f"A first publish needs a thumbnail, and {PUBLISH_FILE} names none."))
    elif not (isinstance(thumbnail, str) and Path(thumbnail).suffix.lower() in IMAGES and _names_file(folder, thumbnail)):
        faults.append(
            ("thumbnail_not_image", f"The thumbnail {thumbnail!r} names no image file ({', '.join(IMAGES)}) in the folder.")
        )


def _check_test_inputs(
    folder: Path, interface: list[Any], test_inputs: dict[str, Any], faults: list[tuple[str, str]]
) -> dict[str, Any]:
    """The Test Inputs' faults against ``interface.json``: a name that is no Field, a
    required Field with no value and no default, and a file Field's value that names no
    file in the folder. Answers the Test Run's input, with the defaults filled in."""
    fields = {
        field["name"]: field for field in interface if isinstance(field, dict) and isinstance(field.get("name"), str)
    }
    for name in test_inputs:
        if name not in fields:
            faults.append(("test_input_unknown", f"{TEST_INPUTS} names {name!r}, which {INTERFACE} has no Field for."))
    defaults = {name: field["default"] for name, field in fields.items() if "default" in field}
    test_input = {**defaults, **test_inputs}
    for name, field in fields.items():
        value = test_input.get(name)
        if value is None:
            # A Field without isRequired counts as required.
            if field.get("isRequired", True) is not False:
                faults.append(("test_input_missing", f"The required Field {name!r} has no value in {TEST_INPUTS} and no default."))
        elif field.get("type") == "file":
            for path in value if isinstance(value, list) else [value]:
                if not _names_file(folder, path):
                    faults.append(("test_input_file_missing", f"The file Field {name!r} names {path!r}, no file inside the folder."))
    return test_input


def _key_faults(abyss: Abyss) -> list[tuple[str, str]]:
    """The key's fault, read with ``GET /v1/key``: it is refused, or it does not manage Widgets."""
    try:
        key = abyss._get(abyss._start(None), f"{abyss.base_url}/v1/key", _is_key, "The key answered without a key.")
    except AbyssError as error:
        return [(error.code, error.message)]
    if key.get("manage_widgets") is not True:
        return [
            (
                "manage_widgets_required",
                f"The key {key.get('key')} does not manage Widgets. Make a new key in your Cave, under Your API keys, "
                "with Create a key and Manage Widgets switched on: a key is never given it after it is made.",
            )
        ]
    return []


def _names_file(folder: Path, path: Any) -> bool:
    """Whether ``path`` names a file inside the folder."""
    return isinstance(path, str) and _inside(folder, path) and (folder / path).is_file()


def _inside(folder: Path, path: str) -> bool:
    """Whether ``path`` is inside the folder, whether or not a file is there."""
    return bool(path) and folder.resolve() in (folder / path).resolve().parents


def publish(abyss: Abyss, folder: Path, widget_folder: _Folder, force: bool = False) -> str:
    """Publishes a folder, and answers the Widget's link: a new Widget for a folder that was
    never published, a new version of the same Widget for one that was.

    A Draft's id goes into the Publish File as soon as it is made, and its Candidate's
    number once committed, so a publish that stops is taken up again on the same Draft.
    A published Widget is first compared with the folder, and a Widget that moved on
    Abyss stops the publish before any upload, unless ``force``.
    """
    publish_file = widget_folder.publish_file
    interface = widget_folder.interface
    block = dict(publish_file.get("widget") or {})
    widget = block.get("id")
    # A Widget published already saves only what differs; a new one saves every Listing Field.
    listing: dict[str, Any] | None = None
    changes = _listing_fields(publish_file)
    send_thumbnail = bool(publish_file.get("thumbnail"))
    if "version" in block:
        listing, changes, send_thumbnail = _compare(abyss, folder, block, publish_file, force)
        base_version = listing["live_version"]
    elif widget is None:
        draft = _expect(
            abyss._send(abyss._start(None), "POST", f"{abyss.base_url}/v1/widgets", retries=0),
            _is_widget,
            "The Draft answered without an id.",
        )
        widget = draft["id"]
        block["id"] = widget
        _write_block(folder, publish_file, block)
        print(f"Made the Draft {widget}.")
        base_version = None
    else:
        print(f"Publishing the Draft {widget}.")
        base_version = block.get("candidate")
    widget_url = abyss._widget_url(widget)

    base = json.dumps({"base_version": base_version}).encode()
    opened = _expect(
        abyss._send(abyss._start(None), "POST", f"{widget_url}/versions", JSON, base),
        _is_project_version,
        "The version answered without its number, form and Junk list.",
    )
    sent, left_out = _folder_files(folder, opened["junk"], publish_file.get("thumbnail"))
    for path in left_out:
        print(f"Left out {path}")
    upload = opened["upload"]
    for path in sent:
        fields = {**upload["fields"], "key": f"{upload['prefix']}/{path}"}
        data = (folder / path).read_bytes()
        abyss._store(abyss._start(None), upload["url"], fields, path, Path(path).name, data)
    print(f"Sent {len(sent)} files.")

    version = opened["version"]
    commit = json.dumps({} if interface is None else {"interface": interface}).encode()
    candidate = _expect(
        abyss._send(abyss._start(None), "POST", f"{widget_url}/versions/{version}/commit", JSON, commit),
        _is_candidate,
        "The commit answered without a Candidate.",
    )
    block["candidate"] = candidate["version"]
    _write_block(folder, publish_file, block)

    print(f"Test Run of version {candidate['version']}...")
    run = _test_run(abyss, folder, widget, candidate["version"], widget_folder.test_input, interface)
    if run["status"] == "failed":
        _print_logs(run.get("logs"))
        error = run.get("error") or {}
        raise AbyssError(
            error.get("code", "platform_fault"),
            f"The Test Run {run['id']} failed, so nothing was published. {error.get('message', '')}".rstrip(),
            run_id=run["id"],
        )

    thumbnail = publish_file.get("thumbnail") if send_thumbnail else None
    if listing is None or changes or thumbnail:
        listing = _save_listing(abyss, folder, widget, changes, thumbnail)
    if thumbnail:
        block["thumbnail_sha256"] = _sha256(folder / thumbnail)
    block["listing_revision"] = listing["listing_revision"]
    _write_block(folder, publish_file, block)
    published = _expect(
        abyss._send(abyss._start(None), "POST", f"{widget_url}/publish"),
        _is_widget,
        "The publish answered without the Widget.",
    )
    block.pop("candidate")
    block["version"] = candidate["version"]
    _write_block(folder, publish_file, block)
    return str(published["url"])


def _read_listing(abyss: Abyss, widget: str) -> dict[str, Any]:
    """Reads a Widget's Listing Fields with its listing revision and its live version."""
    return abyss._get(
        abyss._start(None),
        f"{abyss._widget_url(widget)}/listing",
        lambda value: _is_listing(value) and "live_version" in value,
        "The listing answered without its revision and its live version.",
    )


@dataclass
class _Beside:
    """A published Widget's listing on Abyss, beside the folder that was its last publish or pull."""

    listing: dict[str, Any]
    changes: dict[str, Any]
    """The Publish File's Listing Fields whose value is not the website's."""
    thumbnail_changed: bool
    """The folder's thumbnail is not the one last sent or pulled."""
    listing_moved: bool
    code_moved: bool


def _beside(abyss: Abyss, folder: Path, block: dict[str, Any], publish_file: dict[str, Any]) -> _Beside:
    """Reads the Widget's listing and prints it beside the folder. The Widget moved when
    its listing revision or its live version is not the block's."""
    widget = block["id"]
    listing = _read_listing(abyss, widget)
    changes = {name: value for name, value in _listing_fields(publish_file).items() if listing.get(name) != value}
    thumbnail = publish_file.get("thumbnail")
    path = folder / thumbnail if isinstance(thumbnail, str) and thumbnail else None
    beside = _Beside(
        listing,
        changes,
        path is not None and (not path.is_file() or _sha256(path) != block.get("thumbnail_sha256")),
        listing["listing_revision"] != block.get("listing_revision"),
        listing["live_version"] != block.get("version"),
    )

    print(f"{widget} on Abyss beside the folder:")
    for name, value in changes.items():
        print(f"  {name}: {_shown(listing.get(name))} on Abyss, {_shown(value)} in the folder")
    if beside.thumbnail_changed:
        print(f"  thumbnail: {thumbnail} changed in the folder")
    if beside.listing_moved:
        print("  listing: changed on Abyss since the folder's last publish or pull")
    if beside.code_moved:
        print(f"  code: version {listing['live_version']} is live on Abyss, the folder's is version {block.get('version')}")
    else:
        print(f"  code: version {listing['live_version']} is live on Abyss, as in the folder")
    if not (changes or beside.thumbnail_changed or beside.listing_moved or beside.code_moved):
        print("  nothing else differs")
    return beside


def _moved(beside: _Beside) -> str:
    """What moved on Abyss, in words: its listing, its code, or both."""
    return " and ".join(
        what for what, did in (("its listing", beside.listing_moved), ("its code", beside.code_moved)) if did
    )


def _compare(
    abyss: Abyss, folder: Path, block: dict[str, Any], publish_file: dict[str, Any], force: bool
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Prints the Widget beside the folder, before any upload. A Widget that moved stops
    the publish, unless ``force`` makes the folder win. Answers the listing, the Listing
    Fields to save, and whether to send the thumbnail."""
    widget = block["id"]
    beside = _beside(abyss, folder, block, publish_file)
    moved = beside.listing_moved or beside.code_moved
    if moved and not force:
        pull = "take the website's listing with `abysshub pull`, or " if beside.listing_moved else ""
        raise AbyssError(
            "widget_moved",
            f"{widget} moved on Abyss since this folder's last publish or pull: {_moved(beside)} changed there. "
            f"Nothing was sent. To go on, {pull}publish with --force to make the folder win.",
        )
    if moved:
        print("--force: the folder wins over what moved on Abyss.")
    send_thumbnail = bool(publish_file.get("thumbnail")) and (
        (beside.listing_moved and force) or beside.thumbnail_changed
    )
    return beside.listing, beside.changes, send_thumbnail


def status(abyss: Abyss, folder: Path, publish_file: dict[str, Any]) -> None:
    """Prints a published Widget beside its folder, and sends nothing that changes anything:
    its link, its version, each Listing Field that differs, where each Environment name
    comes from (never a value), and whether it moved since the folder's last publish or pull."""
    block = publish_file["widget"]
    widget = block["id"]
    print(f"{widget}: {abyss.widgets.get(widget).url}")
    beside = _beside(abyss, folder, block, publish_file)
    environment = abyss._get(
        abyss._start(None),
        f"{abyss._widget_url(widget)}/environment",
        _is_environment,
        "The environment answered without its names.",
    )
    print("Environment:")
    for name, entry in sorted(environment["names"].items()):
        print(f"  {name}: from {SOURCES.get(entry.get('source'), entry.get('source'))}")
    if not environment["names"]:
        print("  no names")
    if beside.listing_moved or beside.code_moved:
        print(f"{widget} moved on Abyss since this folder's last publish or pull: {_moved(beside)} changed there.")
        if beside.listing_moved:
            print(f"`abysshub pull {folder}` takes the website's listing into the folder.")
        if beside.code_moved:
            print("Only `abysshub publish --force` replaces the code on Abyss with the folder's.")
    else:
        print(f"{widget} did not move on Abyss since this folder's last publish or pull.")


def pull(abyss: Abyss, folder: Path, publish_file: dict[str, Any]) -> None:
    """Writes the website's value of each Listing Field the Publish File holds into it, the
    Widget's thumbnail to the path the Publish File names, and the listing revision into the
    ``widget`` block, and prints each value it changed. It never touches code: a newer live
    version is only named."""
    block = dict(publish_file.get("widget") or {})
    if "version" not in block:
        raise AbyssError(
            "not_published",
            f"{folder} was never published, so there is nothing to pull. `abysshub publish {folder}` publishes it.",
        )
    thumbnail = publish_file.get("thumbnail")
    if thumbnail and not (
        isinstance(thumbnail, str) and Path(thumbnail).suffix.lower() in IMAGES and _inside(folder, thumbnail)
    ):
        raise AbyssError(
            "thumbnail_not_image",
            f"The thumbnail {thumbnail!r} names no image file ({', '.join(IMAGES)}) inside the folder. Nothing was pulled.",
        )
    widget = block["id"]
    listing = _read_listing(abyss, widget)
    print(f"Pulled the listing of {widget} into the folder:")
    changed = False
    for name, value in _listing_fields(publish_file).items():
        if listing[name] != value:
            print(f"  {name}: {_shown(listing[name])}, was {_shown(value)}")
            publish_file[name] = listing[name]
            changed = True
    url = listing["thumbnail"]
    if isinstance(url, str) and url:
        if not thumbnail:
            suffix = Path(urlsplit(url).path).suffix.lower()
            thumbnail = f"thumbnail{suffix if suffix in IMAGES else '.png'}"
            publish_file["thumbnail"] = thumbnail
        answered, read = abyss._download(url, None)
        data = _downloaded("the thumbnail", answered, read())
        path = folder / thumbnail
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"  thumbnail: written to {thumbnail}")
            changed = True
        block["thumbnail_sha256"] = hashlib.sha256(data).hexdigest()
    if not changed:
        print("  nothing changed")
    block["listing_revision"] = listing["listing_revision"]
    _write_block(folder, publish_file, block)
    if listing["live_version"] != block["version"]:
        print(
            f"The code on Abyss is newer: version {listing['live_version']} is live, the folder's is version "
            f"{block['version']}. A pull never touches code: only `abysshub publish --force` replaces it with the folder's."
        )


def _folder_files(folder: Path, junk: dict[str, Any], thumbnail: str | None) -> tuple[list[str], list[str]]:
    """The folder's files to send, and what it leaves out, by their paths in the folder:
    what the Junk list names, the Publish File, its thumbnail, and a root ``.env`` with its
    variants. A folder that is left out is named once, with a ``/``."""
    names = junk.get("names") or []
    markers = junk.get("markers") or []
    root_names = [*(junk.get("root") or []), *ROOT_ENV]
    skipped = {PUBLISH_FILE}
    if thumbnail:
        skipped.add(Path(thumbnail).as_posix())
    sent: list[str] = []
    left_out: list[str] = []
    for top, dirs, files in os.walk(folder):
        here = Path(top)
        at_root = here == folder
        kept_dirs = []
        for name in sorted(dirs):
            path = here / name
            if any(fnmatchcase(name, pattern) for pattern in names) or _holds_marker(path, markers):
                left_out.append(f"{path.relative_to(folder).as_posix()}/")
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            relative = (here / name).relative_to(folder).as_posix()
            if (
                any(fnmatchcase(name, pattern) for pattern in names)
                or (at_root and any(fnmatchcase(name, pattern) for pattern in root_names))
                or relative in skipped
            ):
                left_out.append(relative)
            else:
                sent.append(relative)
    return sent, left_out


def _test_run(
    abyss: Abyss,
    folder: Path,
    widget: str,
    version: int,
    test_input: dict[str, Any],
    interface: list[Any] | None,
) -> dict[str, Any]:
    """Makes the Test Run of the Candidate from its input and waits for its ending,
    as ``run()`` waits. A file Field's value is a path in the folder, uploaded for that
    Candidate. Answers the run, failed or not."""
    file_fields = {
        field.get("name") for field in interface or [] if isinstance(field, dict) and field.get("type") == "file"
    }

    def value(name: str, item: Any) -> Any:
        if name not in file_fields:
            return item
        if isinstance(item, list):
            return [file(str(folder / path)) if isinstance(path, str) else path for path in item]
        return file(str(folder / item)) if isinstance(item, str) else item

    input = {name: value(name, item) for name, item in test_input.items()}
    call = abyss._start(None)
    press = abyss._press(call, widget, input, None, None, hold=True, version=version)
    reply = press if _has_ended(press) else abyss._hold(call, abyss._wait_url(press), _has_ended)
    assert reply.run is not None
    return reply.run


def _save_listing(
    abyss: Abyss, folder: Path, widget: str, save: dict[str, Any], thumbnail: str | None
) -> dict[str, Any]:
    """Saves these Listing Fields, and sends the thumbnail at that path in the folder
    first, if any. Answers the listing as saved."""
    widget_url = abyss._widget_url(widget)
    save = dict(save)
    if thumbnail:
        path = folder / thumbnail
        data = path.read_bytes()
        call = abyss._start(None)
        body = json.dumps({"filename": path.name, "size": len(data)}).encode()
        grant = parse_upload(
            _expect(
                abyss._send(call, "POST", f"{widget_url}/listing/thumbnail", JSON, body),
                _is_upload,
                "The thumbnail answered without an id and a form.",
            )
        )
        abyss._store(call, grant.upload.url, grant.upload.fields, "thumbnail", path.name, data)
        save["thumbnail"] = grant.id
    return _expect(
        abyss._send(abyss._start(None), "PATCH", f"{widget_url}/listing", JSON, json.dumps(save).encode()),
        _is_listing,
        "The listing answered without its revision.",
    )


def _listing_fields(publish_file: dict[str, Any]) -> dict[str, Any]:
    """The Listing Fields the Publish File holds, ``private`` unless it says."""
    fields = {name: publish_file[name] for name in LISTING_FIELDS if name in publish_file}
    fields.setdefault("visibility", "private")
    return fields


def _sha256(path: Path) -> str:
    """The SHA-256 of a file, which tells whether the thumbnail changed since it was sent."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shown(value: Any) -> str:
    """A Listing Field's value as JSON, as the Publish File writes it."""
    return json.dumps(value, ensure_ascii=False)


def _read_json(path: Path, kind: str, shape: type, faults: list[tuple[str, str]]) -> Any:
    """Reads a JSON file of the folder, or adds its fault and answers None: ``<kind>_missing``
    when it is absent, ``<kind>_invalid`` when it is not JSON of that shape."""
    try:
        value = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        faults.append((f"{kind}_missing", f"The folder has no {path.name}."))
        return None
    except (OSError, ValueError) as error:
        faults.append((f"{kind}_invalid", f"{path.name} is not valid JSON: {error}"))
        return None
    if not isinstance(value, shape):
        faults.append((f"{kind}_invalid", f"{path.name} is not a JSON {'object' if shape is dict else 'array'}."))
        return None
    return value


def _write_block(folder: Path, publish_file: dict[str, Any], block: dict[str, Any]) -> None:
    """Writes the ``widget`` block into the Publish File: which Widget the folder is."""
    publish_file["widget"] = block
    (folder / PUBLISH_FILE).write_text(json.dumps(publish_file, indent=2, ensure_ascii=False) + "\n", "utf-8")


def _holds_marker(path: Path, markers: list[str]) -> bool:
    """Whether a folder holds a marker of a virtual environment: a file, or a folder when it ends in ``/``."""
    for marker in markers:
        if marker.endswith("/") and (path / marker.rstrip("/")).is_dir():
            return True
        if not marker.endswith("/") and (path / marker).is_file():
            return True
    return False


def _print_logs(logs: Any) -> None:
    """Prints a Test Run's logs, which may be any JSON value."""
    print("The Test Run's logs:", file=sys.stderr)
    if logs is None:
        print("(none)", file=sys.stderr)
    elif isinstance(logs, str):
        print(logs, file=sys.stderr)
    elif isinstance(logs, list):
        for line in logs:
            print(line if isinstance(line, str) else json.dumps(line, ensure_ascii=False), file=sys.stderr)
    else:
        print(json.dumps(logs, indent=2, ensure_ascii=False), file=sys.stderr)


def _is_project_version(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("version"), int):
        return False
    upload = value.get("upload")
    return (
        isinstance(upload, dict)
        and isinstance(upload.get("url"), str)
        and isinstance(upload.get("fields"), dict)
        and isinstance(upload.get("prefix"), str)
        and isinstance(value.get("junk"), dict)
    )


def _is_candidate(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("version"), int)


def _is_listing(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("listing_revision"), str)


def _is_environment(value: Any) -> bool:
    names = value.get("names") if isinstance(value, dict) else None
    return isinstance(names, dict) and all(isinstance(entry, dict) for entry in names.values())
