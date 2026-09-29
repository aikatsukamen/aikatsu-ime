#!/usr/bin/env python3
"""data/*.csv の健全性チェック.

  python src/validate.py

エラーがあれば終了コード 1 を返すので、そのままCIで使える。
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CONFIG_DIR, POS_MAP, Entry, load_all_categories, load_json  # noqa: E402

# よみに使える文字: ひらがな・長音符・繰り返し記号
READING_RE = re.compile(r"^[ぁ-んー゛゜ゝゞ]+$")
MAX_READING_LEN = 60


def check(entries: list[Entry]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []

    # 同一カテゴリ内の重複はエラー。カテゴリをまたぐ重複は許容する
    # （例: アイカツフレンズ！のユニット名はブランド名としても使われる）。
    # build.py は辞書の組み立て時にカテゴリをまたいで (よみ, 単語) を重複除去する。
    by_key: dict[tuple[str, str, str], list[Entry]] = defaultdict(list)

    for e in entries:
        loc = e.source
        if not e.reading:
            errors.append(f"{loc}: よみが空")
        if not e.surface:
            errors.append(f"{loc}: 単語が空")
        if e.reading and not READING_RE.match(e.reading):
            errors.append(f"{loc}: よみ '{e.reading}' にひらがな以外が含まれる（MS-IMEが弾く）")
        if len(e.reading) > MAX_READING_LEN:
            errors.append(f"{loc}: よみが長すぎる ({len(e.reading)}文字)")
        if e.pos not in POS_MAP:
            errors.append(f"{loc}: 未定義の品詞 '{e.pos}'")
        if "\t" in e.surface or "\n" in e.surface:
            errors.append(f"{loc}: 単語にタブ/改行が含まれる")
        by_key[(e.category, e.reading, e.surface)].append(e)

        try:
            (e.reading + e.surface).encode("cp932")
        except UnicodeEncodeError:
            warns.append(f"{loc}: '{e.surface}' はShift_JIS化できない（ATOK Shift_JIS版から除外される）")

    for key, dups in by_key.items():
        if len(dups) > 1:
            locs = ", ".join(d.source for d in dups)
            errors.append(f"よみ・単語の重複: {key[1]} / {key[2]} ({locs})")

    return errors, warns


def main() -> int:
    categories_cfg = load_json(CONFIG_DIR / "categories.json")
    dictionaries_cfg = load_json(CONFIG_DIR / "dictionaries.json")

    pool = load_all_categories(categories_cfg)
    all_entries = [e for v in pool.values() for e in v]

    errors, warns = check(all_entries)

    # dictionaries.json が存在しないカテゴリを参照していないか
    known = set(pool.keys())
    for spec in dictionaries_cfg["dictionaries"]:
        cats = spec.get("categories", ["*"])
        if cats != ["*"]:
            for c in cats:
                if c not in known:
                    errors.append(f"dictionaries.json: 辞書 '{spec['id']}' が未定義カテゴリ '{c}' を参照")

    for w in warns:
        print(f"[warn]  {w}")
    for e in errors:
        print(f"[error] {e}")

    print(f"\n{len(all_entries)} entries checked / {len(errors)} errors / {len(warns)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())