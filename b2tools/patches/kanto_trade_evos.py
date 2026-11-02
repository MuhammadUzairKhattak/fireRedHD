"""FireRedHD slice a5.3: Kanto trade evolutions made in-game, without a link cable.

Data-only (no code, no clang, no `shops`, no intro chain). It installs trade_evos' two ROM-agnostic steps and
defers the third:
  1. a/0/1/9 evolution table: Black 2's trade-only evolutions get in-game methods (level / bag item / species-in-party)
     from data/kanto_trade_evos.json, keeping Black 2's own link-trade entries (keep_trade_methods).
  2. a/0/2/4 item data: every item an ITEM evolution uses gets the Bag "Use" of an evolution stone.
The shop-append (trade_evos step 3, which sells the evolution items) is deliberately skipped: it needs Kanto marts
(the `shops` content phase, Phase 2/3). The evolution *mechanic* lands now; the item *acquisition* follows with
content. Every archive keeps its size, so the ROM file table and savestates are unchanged (boot-safe).

This reuses the generic engine patch (b2tools/patches/trade_evos.py) unchanged and follows the Kanto convention of
never editing the Hoenn path: only the data source (kanto_trade_evos.json) and the shop step differ."""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import trade_evos          # the generic data patch, imported unchanged


def _data():
    return json.load(open(os.path.join(ROOT, 'data', 'kanto_trade_evos.json')))


def apply(files):
    import narcio
    data = _data()
    C = trade_evos.constants()
    trade = {C['EVO_METHOD_TRADE'], C['EVO_METHOD_TRADE_WITH_ITEM'], C['EVO_METHOD_TRADE_WITH_SPECIES']}
    new = trade_evos.table(data, C)
    out = []

    # 1. evolutions: exactly the species with a trade method in Black 2's table, other evolutions kept
    vanilla = narcio.load(trade_evos.VANILLA, trade_evos.ARC_EVO)
    evo = narcio.load(files, trade_evos.ARC_EVO)
    traders = {i for i, rec in enumerate(vanilla) if any(m in trade for m, _, _ in trade_evos.entries_of(rec))}
    keep = data.get('keep_trade_methods', False)
    assert traders == set(new), f'trade species not covered: {sorted(traders - set(new))}, ' \
                                f'not trade species: {sorted(set(new) - traders)}'
    for sp, lst in new.items():
        kept = [e for e in trade_evos.entries_of(vanilla[sp]) if e[0] not in trade]
        assert all(e in lst for e in kept), f'species {sp}: a non-trade evolution was lost: {kept} vs {lst}'
        assert not any(e[0] in trade for e in lst), f'species {sp}: still a trade method'
        full = lst + ([e for e in trade_evos.entries_of(vanilla[sp]) if e[0] in trade] if keep else [])
        assert evo[sp] in (vanilla[sp], trade_evos.pack(lst), trade_evos.pack(full)), \
            f'species {sp}: evolution file changed by another patch'
        evo[sp] = trade_evos.pack(full)
    narcio.save(files, trade_evos.ARC_EVO, evo)
    out.append(f'{len(new)} species' + (" (+ Black 2's own trade methods)" if keep else ''))

    # 2. items an EVO_METHOD_ITEM evolution uses: the Bag "Use" of an evolution stone
    items = narcio.load(files, trade_evos.ARC_ITEM)
    field, party, flags = trade_evos.stone_use(items, C)
    used = sorted({p for lst in new.values() for m, p, _ in lst if m == C['EVO_METHOD_ITEM']})
    changed = []
    for it in used:
        d = bytearray(items[it])
        if (d[0xA], d[0xC], d[0x11] & flags) == (field, party, flags):
            continue                                   # a stone already (Water Stone), or patched before
        assert d[0xA] == 0 and d[0xC] == 0 and not any(d[0x10:]), f'item {it}: unexpected item data {d.hex()}'
        assert not d[8] & 0x20, f'item {it}: not holdable'
        d[0xA], d[0xC], d[0x11] = field, party, flags
        items[it] = bytes(d)
        changed.append(it)
    narcio.save(files, trade_evos.ARC_ITEM, items)
    out.append(f'Bag use like a stone: items {changed}')

    # 3. shop-append deferred to the Kanto marts (shops) content phase: see the module docstring.
    out.append('shop-append deferred (needs Kanto marts / shops)')
    return 'kanto trade evolutions: ' + '; '.join(out)
