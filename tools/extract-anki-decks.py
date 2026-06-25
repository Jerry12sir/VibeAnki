import html
import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

DECKS = [
    {
        "apkg": ROOT / "Shin_Kanzen_Master_Vocabulary_JLPT_N3_Official_Definitions.apkg",
        "output": DATA_DIR / "shinkanzen-n3.json",
        "source_name": "Shin Kanzen Master Vocabulary JLPT N3",
        "kind": "shinkanzen",
    },
    {
        "apkg": ROOT / "Kaishi_15k_-_Basic_Japanese_Vocabulary.apkg",
        "output": DATA_DIR / "kaishi-15k.json",
        "source_name": "Kaishi 1.5k",
        "kind": "kaishi",
    },
]


def strip_html(value):
    text = re.sub(r"\[sound:[^\]]+\]", "", str(value or ""))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def kata_to_hira(value):
    return "".join(
        chr(ord(char) - 0x60) if "\u30a1" <= char <= "\u30f6" else char
        for char in str(value or "")
    )


def furigana_to_hiragana(value):
    text = strip_html(value)
    if "[" in text and "]" in text:
        text = re.sub(r"([^\[\]\s]+)\[([^\]]+)\]", lambda match: match.group(2), text)
    text = kata_to_hira(text)
    text = re.sub(r"[\s・･~～]+", "", text)
    text = re.sub(r"[^\u3040-\u309fー]", "", text)
    return text.strip()


def open_collection(apkg):
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    archive = zipfile.ZipFile(apkg)
    db_name = "collection.anki21" if "collection.anki21" in archive.namelist() else "collection.anki2"
    archive.extract(db_name, temp_dir.name)
    con = sqlite3.connect(str(Path(temp_dir.name) / db_name))
    return temp_dir, archive, con


def note_rows(con):
    cur = con.cursor()
    models_raw = cur.execute("select models from col").fetchone()[0]
    models = json.loads(models_raw)
    for nid, mid, flds, tags in cur.execute("select id, mid, flds, tags from notes order by id"):
        names = [field["name"] for field in models[str(mid)]["flds"]]
        values = dict(zip(names, flds.split("\x1f")))
        yield nid, values, tags.split()


def primary_lesson_tag(tags):
    numeric = sorted(tag for tag in tags if re.fullmatch(r"\d+", tag))
    return numeric[0] if numeric else "unsorted"


def extract_shinkanzen(deck):
    cards = []
    temp_dir, archive, con = open_collection(deck["apkg"])
    try:
        for index, (nid, fields, tags) in enumerate(note_rows(con), 1):
            expression = strip_html(fields.get("Expression"))
            meaning = strip_html(fields.get("Meaning"))
            if not expression or not meaning:
                continue
            lesson_tag = primary_lesson_tag(tags)
            cards.append({
                "id": f"shinkanzen-n3-{index:04d}",
                "level": "N3",
                "lesson": f"Lesson {lesson_tag}",
                "section": "Shinkanzen",
                "source": "anki",
                "sourceName": deck["source_name"],
                "number": index,
                "japanese": expression,
                "reading": furigana_to_hiragana(fields.get("Reading")),
                "meaning": meaning,
                "category": "word",
                "example": strip_html(fields.get("Notes")),
            })
    finally:
        con.close()
        archive.close()
        temp_dir.cleanup()
    return cards


def extract_kaishi(deck):
    cards = []
    temp_dir, archive, con = open_collection(deck["apkg"])
    try:
        for index, (nid, fields, tags) in enumerate(note_rows(con), 1):
            word = strip_html(fields.get("Word"))
            meaning = strip_html(fields.get("Word Meaning"))
            if not word or not meaning or word.startswith("Welcome to Kaishi"):
                continue
            cards.append({
                "id": f"kaishi-15k-{len(cards) + 1:04d}",
                "level": "Kaishi",
                "lesson": "Kaishi 1.5k",
                "section": "Core Vocabulary",
                "source": "anki",
                "sourceName": deck["source_name"],
                "number": len(cards) + 1,
                "japanese": word,
                "reading": furigana_to_hiragana(fields.get("Word Reading") or fields.get("Word Furigana")),
                "meaning": meaning,
                "category": "word",
                "example": strip_html(fields.get("Sentence")),
                "exampleTranslation": strip_html(fields.get("Sentence Meaning")),
            })
    finally:
        con.close()
        archive.close()
        temp_dir.cleanup()
    return cards


def main():
    DATA_DIR.mkdir(exist_ok=True)
    for deck in DECKS:
        if not deck["apkg"].exists():
            print(f"Skipping missing source deck: {deck['apkg'].name}")
            continue
        cards = extract_shinkanzen(deck) if deck["kind"] == "shinkanzen" else extract_kaishi(deck)
        deck["output"].write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(cards)} cards to {deck['output'].relative_to(ROOT)}")


if __name__ == "__main__":
    main()
