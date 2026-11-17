#!/usr/bin/env python3
"""Merge Jild 12 tashreeh chunks into jild-12.json.

Re-runnable: reads every jild-12-chunk-*.json listed in the manifest,
merges in chunk order, validates (unique ids, page coverage vs manifest,
no empty jawab), writes jild-12.json, and updates the manifest statuses.

Manifest structure: entry "10" is a "split-halves" placeholder
(no file on disk) — its halves 10a/10b are separate entries with their
own files. Placeholders are skipped.

SPECIAL CASES (coordinator instructions, verified on disk by the parent):
6 same-id pairs are ONE mas'ala split across chunks and must be
COMBINED into a single item, NOT renamed by the duplicate-id rule.
After combining all 6, the merged file has 338 items (344 - 6)
covering 588 unique pages. Combine rules per id (first = earlier chunk,
second = later chunk, ordered by min page):
  masala 20:      sawal from first; jawab = first + second concatenated.
  masala 137:     sawal from first; jawab = first + second concatenated.
  masala 240-241: sawal from first (the full sawal); jawab = first + second concatenated.
  masala 271:     sawal from first; jawab = first + second concatenated.
  masala 289:     SPECIAL — the opposite of the Jild 11 masala-16 case:
                  sawal = first's sawal + second's sawal-tail CONCATENATED
                  (both halves carry parts of the same question — the
                  p. 587 portion in 10a and the Mukhtasar/Sharh al-Wiqaya
                  quotation tail on p. 588 in 10b; do NOT discard either);
                  jawab from second.
  masala 303:     sawal from first; jawab = first + second concatenated.
For every combined item: pages = union of both halves' pages,
start_page = min, notes = both files' notes combined.

Distinct items that merely look similar are NOT combined — they already
have distinct ids and stay separate: the printed number 274 occurs twice
(jild12-masala-274 p. 569 + jild12-p581 p. 581); jild12-masala-101-102 is
one printed item, not a duplicate.

NOTE: the two fasl headings (jild12-fasl-awwal p. 211, jild12-fasl-doom
p. 227) share their pages with masail 79 and 80-86 by design — pp. 211
and 227 appear in two items each; unique-page count is still 588, but
the sum of pages arrays exceeds it. The coverage check below uses a
SET, so shared pages are expected and fine.

Duplicate-id rule (Jild 4 precedent) still applies to any OTHER
duplicate: earliest keeps the plain id, later ones get "-p<startpage>".
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))

# id -> (sawal source, jawab source); 'first' = earlier chunk, 'second' = later.
COMBINES = {
    'jild12-masala-20':      ('first', 'concat'),
    'jild12-masala-137':     ('first', 'concat'),
    'jild12-masala-240-241': ('first', 'concat'),
    'jild12-masala-271':     ('first', 'concat'),
    'jild12-masala-289':     ('concat', 'second'),   # SPECIAL: concatenate BOTH sawals
    'jild12-masala-303':     ('first', 'concat'),
}


def combine_pair(item_id, first, second):
    sawal_rule, jawab_rule = COMBINES[item_id]
    if sawal_rule == 'concat':
        sawal = (first.get('tashreeh_sawal', '') or '') + (second.get('tashreeh_sawal', '') or '')
    elif sawal_rule == 'first':
        sawal = first.get('tashreeh_sawal', '')
    else:
        sawal = second.get('tashreeh_sawal', '')
    if jawab_rule == 'concat':
        jawab = (first.get('tashreeh_jawab', '') or '') + (second.get('tashreeh_jawab', '') or '')
    else:
        jawab = (second.get('tashreeh_jawab', '') or '')
    combined = {
        'id': item_id,
        'title': first.get('title') or second.get('title', ''),
        'volume_id': 55,
        'pages': sorted(set(first['pages']) | set(second['pages'])),
        'start_page': min(first['pages']),
        'tashreeh_sawal': sawal,
        'tashreeh_jawab': jawab,
        'notes': list(first.get('notes') or []) + list(second.get('notes') or []),
    }
    return combined


def main():
    manifest = json.load(open(os.path.join(BASE, 'chunks-manifest-jild12.json')))
    all_items = []
    merged_chunks = []
    for entry in manifest['chunks']:
        nn = entry['chunk']
        if entry.get('status') == 'split-halves':
            print(f'chunk {nn}: split-halves placeholder — halves are separate entries, skipping')
            continue
        path = os.path.join(BASE, entry['file'])
        if not os.path.exists(path):
            print(f'chunk {nn}: not yet written')
            continue
        try:
            d = json.load(open(path, encoding='utf-8'))
        except json.JSONDecodeError as e:
            # File may still be streaming from its translator; skip it
            # for now instead of crashing the whole merge.
            print(f'chunk {nn}: not valid JSON yet ({e}) — skipping for now')
            continue
        items = d['masail']
        # Normalize: some translators omit start_page; derive it from pages.
        for it in items:
            if 'start_page' not in it:
                assert it.get('pages'), f'chunk {nn} item {it.get("id")} has no pages'
                it['start_page'] = it['pages'][0]
                print(f'chunk {nn}: derived start_page={it["start_page"]} for {it["id"]}')
            assert it['start_page'] == min(it['pages']), \
                f'chunk {nn} item {it["id"]}: start_page != first page'
        all_items.extend(items)
        merged_chunks.append(nn)
        entry['status'] = 'merged'
        print(f'chunk {nn}: {len(items)} items merged')
    print(f'items before combines: {len(all_items)}')
    # COMBINE the 6 same-id pairs (one mas'ala split across chunks).
    for item_id, (sawal_rule, jawab_rule) in COMBINES.items():
        pair = [it for it in all_items if it['id'] == item_id]
        assert len(pair) == 2, f'expected exactly 2 {item_id} items, found {len(pair)}'
        pair.sort(key=lambda it: min(it['pages']))
        first, second = pair
        if item_id == 'jild12-masala-289':
            assert first.get('tashreeh_sawal'), 'masala-289: first half must carry sawal part 1'
            assert second.get('tashreeh_sawal'), 'masala-289: second half must carry the sawal tail'
            assert not first.get('tashreeh_jawab'), 'masala-289: first half jawab must be empty (partner holds it)'
        combined = combine_pair(item_id, first, second)
        assert combined['tashreeh_jawab'], f'{item_id}: combined jawab is empty!'
        assert combined['tashreeh_sawal'], f'{item_id}: combined sawal is empty!'
        all_items = [it for it in all_items if it['id'] != item_id]
        all_items.append(combined)
        print(f'COMBINED {item_id}: pages {combined["pages"]}, '
              f'sawal {len(combined["tashreeh_sawal"])} chars, '
              f'jawab {len(combined["tashreeh_jawab"])} chars, notes {len(combined["notes"])}')
    # de-duplicate any OTHER ids: earliest keeps plain id, later ones get -p<startpage>
    seen = {}
    for it in all_items:
        if it['id'] in seen:
            new_id = f"{it['id']}-p{it['start_page']}"
            print(f'DUPLICATE ID {it["id"]} (start {it["start_page"]}) -> renamed {new_id}')
            it['id'] = new_id
        seen[it['id']] = True
    ids = [it['id'] for it in all_items]
    assert len(ids) == len(set(ids)), f'STILL DUPLICATE IDS: {[i for i in ids if ids.count(i) > 1]}'
    empty = [it['id'] for it in all_items if not it.get('tashreeh_jawab')]
    assert not empty, f'EMPTY JAWAB: {empty}'
    pages = set()
    for it in all_items:
        pages.update(it['pages'])
    expected = set()
    for entry in manifest['chunks']:
        if entry['chunk'] in merged_chunks:
            expected.update(range(entry['start_page'], entry['end_page'] + 1))
            expected.difference_update(entry['missing_pages'])
    missing_covered = expected - pages
    extra = pages - expected
    print(f'total items: {len(all_items)} | pages covered: {len(pages)} | expected: {len(expected)}')
    print(f'uncovered expected pages: {sorted(missing_covered)}')
    print(f'extra pages (outside merged chunks): {sorted(extra)}')
    assert not missing_covered, 'pages missing from merged chunks!'
    assert not extra, 'pages outside merged chunks!'
    assert len(all_items) == 338, f'expected 338 items after combines, got {len(all_items)}'
    assert len(pages) == 588, f'expected 588 pages, got {len(pages)}'
    # sort by start_page for the final file
    all_items.sort(key=lambda it: it['start_page'])
    with open(os.path.join(BASE, 'jild-12.json'), 'w', encoding='utf-8') as f:
        json.dump({'masail': all_items}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(BASE, 'chunks-manifest-jild12.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f'WROTE jild-12.json: {len(all_items)} items, {len(pages)} pages, chunks merged: {merged_chunks}')


if __name__ == '__main__':
    main()
