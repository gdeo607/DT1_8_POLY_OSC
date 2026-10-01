#!/usr/bin/env python3
"""Make a SOPHIE, NEIGHBOR or DIGISLICER build that combines through digichain.

    python3 tools/chain_patch.py MODDIR      (a copy of digisophie, digineighbor or digislicer)

digisophie, digineighbor and digislicer each patch some of the same firmware places (the SRC page's
label, value, knob and range functions, the render step after playback). mods/digichain owns those
places once and passes each call to the handler of the machine it is for. This moves the mod's
sites for those places out of its mod.json, so digichain calls its handlers instead; its code is not
touched. It also adds digichain to what the mod requires and "-chain" to its version.

It changes nothing, and exits 2, unless every site it moves is exactly the one it expects (address,
stock bytes, op and handler name): a mod whose sites changed upstream is then built as it is.
"""
import json
import os
import re
import sys

# address -> (stock, op, the handler digichain calls) for each mod
MOVED = {
    'digisophie': {
        '0x400657cc': ('7203202f0004', 'jmp', 'ds_layout'),
        '0x4000fe8a': ('222f00080c81000000a4', 'jmp', 'ds_lab_short'),
        '0x4000feac': ('222f00080c81000000a4', 'jmp', 'ds_lab_long'),
        '0x4000f324': ('4fefffec48d70c1c', 'jmp', 'ds_val_text'),
        '0x4000f2bc': ('4fefffec48d7007c', 'jmp', 'ds_knob_gfx'),
        '0x40065794': ('222f00040c81000000a4', 'jmp', 'ds_ui_rec'),
        '0x400657ee': ('222f00040c81000000a4', 'jmp', 'ds_pop_text'),
        '0x40077fba': ('49f94199e444', 'jsr', 'ds_inject_s'),
        '0x4000ff20': ('4eb940078f0c', 'keep2', 'ds_prange'),
        '0x400100c4': ('4eb940078f0c', 'keep2', 'ds_prange'),
        '0x4000f534': ('4eb940078f0c', 'keep2', 'ds_prange'),
        '0x4000f5fc': ('45f940078f0c', 'keep2', 'ds_prange_f'),
    },
    'digineighbor': {
        '0x400657cc': ('7203202f0004', 'jmp', 'nb_layout'),
        '0x4000fe8a': ('222f00080c81000000a4', 'jmp', 'nb_lab_short'),
        '0x4000feac': ('222f00080c81000000a4', 'jmp', 'nb_lab_long'),
        '0x4000f324': ('4fefffec48d70c1c', 'jmp', 'nb_val_text'),
        '0x4000f2bc': ('4fefffec48d7007c', 'jmp', 'nb_knob_gfx'),
        '0x40065794': ('222f00040c81000000a4', 'jmp', 'nb_ui_rec'),
        '0x400657ee': ('222f00040c81000000a4', 'jmp', 'nb_pop_text'),
        '0x40077fba': ('49f94199e444', 'jsr', 'nb_inject_s'),
    },
    'digislicer': {
        '0x4000ff20': ('4eb940078f0c', 'keep2', 'dsl_prange'),
        '0x400100c4': ('4eb940078f0c', 'keep2', 'dsl_prange'),
        '0x4000f534': ('4eb940078f0c', 'keep2', 'dsl_prange'),
        '0x4000f5fc': ('45f940078f0c', 'keep2', 'dsl_prange_f'),
    },
}
# the machine each mod's handlers act for, which digichain routes by (mods/digichain/chain.s)
MACHINE = {'digisophie': 7, 'digineighbor': 4, 'digislicer': 5}


def machine_id(moddir, doc):
    """The SRC machine number the mod adds (its core_machines entry's first long), or None."""
    syms = [r[2][4:] for c in doc.get('contribute', []) if c.get('to') == 'core_machines'
            for r in c.get('relocs', []) if str(r[2]).startswith('sym:')]
    for src in doc.get('sources', []):
        if not src.endswith('.s') or not syms:
            continue
        with open(os.path.join(moddir, src)) as fh:
            text = fh.read()
        m = re.search(r'^%s:\s*\.long\s+(\w+)' % re.escape(syms[0]), text, re.M)
        if m:
            v = m.group(1)
            e = re.search(r'\.equ\s+%s\s*,\s*(\w+)' % re.escape(v), text)
            return int(e.group(1) if e else v, 0)
    return None


def patch(doc, moddir='.'):
    """-> the patched mod.json, or raise ValueError saying what does not match."""
    mid = doc.get('id')
    if mid not in MOVED:
        raise ValueError('not a mod digichain knows: %s' % mid)
    want = MOVED[mid]
    sites = doc.get('sites', [])
    found = {}
    for s in sites:
        a = '0x%08x' % int(str(s.get('addr')), 16)
        if a in want:
            found[a] = s
    for a, (stock, op, fn) in want.items():
        s = found.get(a)
        if s is None:
            raise ValueError('%s no longer patches %s' % (mid, a))
        if (s.get('stock', '').lower(), s.get('op'), s.get('target')) != (stock, op, fn):
            raise ValueError('%s patches %s differently now: %s %s %s' % (mid, a, s.get('stock'), s.get('op'),
                                                                         s.get('target')))
    m = machine_id(moddir, doc)
    if m != MACHINE[mid]:
        raise ValueError('%s adds machine %s now, not %d' % (mid, m, MACHINE[mid]))
    out = dict(doc)
    out['sites'] = [s for s in sites if '0x%08x' % int(str(s.get('addr')), 16) not in want]
    out['requires'] = list(dict.fromkeys(list(doc.get('requires', [])) + ['digichain']))
    out['version'] = '%s-chain' % doc['version']
    out['description'] = (doc.get('description', '') + ' This build combines with the other SRC machine '
                          'mods through digichain, which it needs (tools/chain_patch.py moved %d of its sites '
                          'there; its code is unchanged).' % len(want)).strip()
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    moddir = sys.argv[1].rstrip('/')
    path = moddir + '/mod.json'
    with open(path) as fh:
        doc = json.load(fh)
    try:
        out = patch(doc, moddir)
    except ValueError as e:
        print('chain_patch: %s; building it unchanged' % e)
        sys.exit(2)
    with open(path, 'w') as fh:
        json.dump(out, fh, indent=1)
        fh.write('\n')
    print('chain_patch: %s %s: %d sites moved to digichain' % (out['id'], out['version'], len(MOVED[out['id']])))


if __name__ == '__main__':
    main()
