#!/usr/bin/env python3
"""aikatsu-ime 辞書ビルダー.

data/*.csv (中間形式) から各IME向けの辞書ファイルを生成する。
標準ライブラリのみで動作する。

  python src/build.py                 # 全辞書・全形式をビルド
  python src/build.py --dict full     # 特定の辞書だけ
  python src/build.py --format google # 特定の形式だけ
"""
from __future__ import annotations

import argparse
import codecs
import csv
import json
import plistlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DEFAULT_DIST = ROOT / "dist"

# ---------------------------------------------------------------------------
# 品詞マッピング
#
# 中間品詞 -> 各IMEの品詞名。IME側の品詞名が正しいかは環境依存なので、
# 変換がおかしいと感じたらここだけ直せばよい。
# ATOK は製品バージョンによって受け付ける品詞名が異なる可能性がある。
# ---------------------------------------------------------------------------
POS_MAP: dict[str, dict[str, str]] = {
    "person_full": {"google": "人名", "msime": "人名", "atok": "人名"},
    "person_last": {"google": "姓", "msime": "姓", "atok": "姓"},
    "person_first": {"google": "名", "msime": "名", "atok": "名"},
    "org": {"google": "組織", "msime": "組織", "atok": "固有名詞"},
    "proper_noun": {"google": "固有名詞", "msime": "固有名詞", "atok": "固有名詞"},
    "noun": {"google": "名詞", "msime": "名詞", "atok": "名詞"},
}

FORMATS = ("google", "msime", "atok", "macos")

ATOK_HEADER = "!!ATOK_TANGO_TEXT_HEADER_1"


@dataclass
class Entry:
    reading: str
    surface: str
    pos: str
    flags: set[str] = field(default_factory=set)
    note: str = ""
    category: str = ""
    source: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.reading, self.surface)


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_flags(raw: str) -> set[str]:
    return {f.strip() for f in (raw or "").split(";") if f.strip()}


def load_category(meta: dict) -> list[Entry]:
    path = ROOT / meta["file"]
    if not path.exists():
        raise FileNotFoundError(f"CSVが見つからない: {path}")

    default_pos = meta.get("default_pos", "noun")
    default_flags = parse_flags(meta.get("default_flags", ""))

    entries: list[Entry] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for lineno, row in enumerate(reader, start=2):
            reading = (row.get("reading") or "").strip()
            surface = (row.get("surface") or "").strip()
            if not reading and not surface:
                continue  # 空行
            entries.append(
                Entry(
                    reading=reading,
                    surface=surface,
                    pos=(row.get("pos") or "").strip() or default_pos,
                    flags=parse_flags(row.get("flags", "")) | default_flags,
                    note=(row.get("note") or "").strip(),
                    category=meta["id"],
                    source=f"{meta['file']}:{lineno}",
                )
            )
    return entries


def load_all_categories(categories_cfg: dict) -> dict[str, list[Entry]]:
    return {c["id"]: load_category(c) for c in categories_cfg["categories"]}


# ---------------------------------------------------------------------------
# 辞書の組み立て
# ---------------------------------------------------------------------------
def build_entry_list(spec: dict, pool: dict[str, list[Entry]]) -> list[Entry]:
    wanted = spec.get("categories", ["*"])
    if wanted == ["*"]:
        cat_ids = list(pool.keys())
    else:
        cat_ids = wanted

    exclude = set(spec.get("exclude_flags", []))
    include = set(spec.get("include_flags", []))
    prefix = spec.get("reading_prefix", "")

    out: list[Entry] = []
    seen: set[tuple[str, str]] = set()
    for cid in cat_ids:
        if cid not in pool:
            raise KeyError(f"未定義のカテゴリ: {cid}")
        for e in pool[cid]:
            if exclude & e.flags:
                continue
            if include and not (include & e.flags):
                continue
            reading = prefix + e.reading
            key = (reading, e.surface)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Entry(
                    reading=reading,
                    surface=e.surface,
                    pos=e.pos,
                    flags=e.flags,
                    note=e.note,
                    category=e.category,
                    source=e.source,
                )
            )
    out.sort(key=lambda e: (e.reading, e.surface))
    return out


def pos_for(entry: Entry, fmt: str) -> str:
    mapping = POS_MAP.get(entry.pos)
    if mapping is None:
        raise KeyError(f"未定義の品詞 '{entry.pos}' ({entry.source})")
    return mapping[fmt]


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------
def encode_text(text: str, encoding: str) -> bytes:
    if encoding == "utf-16le-bom":
        return codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    if encoding == "utf-8-bom":
        return codecs.BOM_UTF8 + text.encode("utf-8")
    return text.encode(encoding)


def split_encodable(entries: list[Entry], encoding: str) -> tuple[list[Entry], list[tuple[Entry, str]]]:
    """指定エンコーディングで表現できないエントリを分離する。"""
    ok: list[Entry] = []
    ng: list[tuple[Entry, str]] = []
    for e in entries:
        try:
            (e.reading + e.surface + e.note).encode(encoding)
        except UnicodeEncodeError as ex:
            bad = (e.reading + e.surface + e.note)[ex.start:ex.end]
            ng.append((e, bad))
        else:
            ok.append(e)
    return ok, ng


def write_google(entries: list[Entry], path: Path, meta: dict) -> None:
    lines = [f"{e.reading}\t{e.surface}\t{pos_for(e, 'google')}\t{e.note}" for e in entries]
    path.write_bytes(encode_text("\n".join(lines) + "\n", "utf-8"))


def write_msime(entries: list[Entry], path: Path, meta: dict) -> None:
    # Microsoft IME の辞書ツールは UTF-16LE(BOM付き) / CRLF が最も確実。
    # コメント列は環境によって解釈が異なるため出力しない。
    lines = [f"{e.reading}\t{e.surface}\t{pos_for(e, 'msime')}" for e in entries]
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(encode_text(text, "utf-16le-bom"))


def write_atok(entries: list[Entry], path: Path, meta: dict, encoding: str) -> list[tuple[Entry, str]]:
    ok, ng = split_encodable(entries, encoding) if encoding == "cp932" else (entries, [])
    lines = [ATOK_HEADER]
    lines += [f"{e.reading}\t{e.surface}\t{pos_for(e, 'atok')}" for e in ok]
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(encode_text(text, encoding))
    return ng


def write_macos(entries: list[Entry], path: Path, meta: dict) -> None:
    # macOS のユーザ辞書は品詞を持たない。
    data = [{"shortcut": e.reading, "phrase": e.surface} for e in entries]
    with path.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_XML, sort_keys=False)


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="aikatsu-ime 辞書ビルダー")
    ap.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="出力先ディレクトリ")
    ap.add_argument("--dict", dest="dict_ids", action="append", help="ビルドする辞書ID (複数指定可)")
    ap.add_argument("--format", dest="formats", action="append", choices=FORMATS, help="出力形式 (複数指定可)")
    ap.add_argument("--atok-encoding", default="cp932", choices=["cp932", "utf-8"],
                    help="ATOK辞書の文字コード (既定: cp932)。utf-8版も併せて出力される")
    ap.add_argument("--prefix", default="aikatsu", help="出力ファイル名の接頭辞")
    args = ap.parse_args(argv)

    categories_cfg = load_json(CONFIG_DIR / "categories.json")
    dictionaries_cfg = load_json(CONFIG_DIR / "dictionaries.json")

    pool = load_all_categories(categories_cfg)
    total_source = sum(len(v) for v in pool.values())
    print(f"[read] {len(pool)} categories / {total_source} entries")

    specs = dictionaries_cfg["dictionaries"]
    if args.dict_ids:
        wanted = set(args.dict_ids)
        specs = [s for s in specs if s["id"] in wanted]
        missing = wanted - {s["id"] for s in specs}
        if missing:
            print(f"error: 未定義の辞書ID: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    formats = args.formats or list(FORMATS)
    dist = args.dist
    for fmt in formats:
        (dist / fmt).mkdir(parents=True, exist_ok=True)

    manifest = []
    warnings: list[str] = []

    for spec in specs:
        entries = build_entry_list(spec, pool)
        did = spec["id"]
        files = []

        if "google" in formats:
            p = dist / "google" / f"{args.prefix}-{did}.txt"
            write_google(entries, p, spec)
            files.append(str(p.relative_to(dist)))

        if "msime" in formats:
            p = dist / "msime" / f"{args.prefix}-{did}.txt"
            write_msime(entries, p, spec)
            files.append(str(p.relative_to(dist)))

        if "atok" in formats:
            p = dist / "atok" / f"{args.prefix}-{did}.txt"
            ng = write_atok(entries, p, spec, args.atok_encoding)
            files.append(str(p.relative_to(dist)))
            for e, bad in ng:
                warnings.append(
                    f"atok/{did}: '{e.surface}' は {args.atok_encoding} で表現できない文字 '{bad}' を含むため除外 ({e.source})"
                )
            # Unicode を受け付けるATOK向けに UTF-8 版も併置する
            if args.atok_encoding != "utf-8":
                p8 = dist / "atok" / f"{args.prefix}-{did}-utf8.txt"
                write_atok(entries, p8, spec, "utf-8")
                files.append(str(p8.relative_to(dist)))

        if "macos" in formats:
            p = dist / "macos" / f"{args.prefix}-{did}.plist"
            write_macos(entries, p, spec)
            files.append(str(p.relative_to(dist)))

        manifest.append({
            "id": did,
            "label": spec.get("label", did),
            "description": spec.get("description", ""),
            "categories": spec.get("categories", ["*"]),
            "count": len(entries),
            "files": files,
        })
        print(f"[build] {did:16s} {len(entries):5d} entries")

    (dist / "manifest.json").write_text(
        json.dumps({"dictionaries": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for w in warnings:
        print(f"[warn] {w}", file=sys.stderr)

    print(f"[done] -> {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
