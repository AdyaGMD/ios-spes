#!/usr/bin/env python3
"""Report GPU resources from a live spes FDT. Host-only; no MMIO or firmware loads."""
import argparse
import json
from pathlib import Path
from spes_memory import parse


def profile(blob):
    nodes, _ = parse(blob)
    if b'qcom,khaje\0' not in nodes.get('', {}).get('compatible', b''):
        raise ValueError('expected khaje live device tree')
    candidates = [(p, v) for p, v in nodes.items()
                  if b'qcom,kgsl-3d0' in v.get('compatible', b'').split(b'\0')]
    if len(candidates) != 1:
        raise ValueError('expected exactly one KGSL GPU')
    path, gpu = candidates[0]
    chip = int.from_bytes(gpu.get('qcom,chipid', b''), 'big')
    if len(gpu.get('qcom,chipid', b'')) != 4 or chip != 0x06010001:
        raise ValueError('unqualified GPU chip ID; expected spes A610 revision 1')

    def resource(path, props):
        parent = nodes[path.rsplit('/', 1)[0]]
        ac = int.from_bytes(parent.get('#address-cells', b'\0\0\0\2'), 'big')
        sc = int.from_bytes(parent.get('#size-cells', b'\0\0\0\1'), 'big')
        raw = props.get('reg', b'')
        if ac not in (1, 2) or sc not in (1, 2):
            raise ValueError('unsupported resource cells')
        stride = 4 * (ac + sc)
        if not raw or len(raw) % stride:
            raise ValueError('invalid resource lengths')
        names = props.get('reg-names', b'').rstrip(b'\0').split(b'\0')
        if len(names) != len(raw) // stride or not all(names):
            raise ValueError('missing resource names')
        windows = []
        for i, offset in enumerate(range(0, len(raw), stride)):
            base = int.from_bytes(raw[offset:offset + ac * 4], 'big')
            size = int.from_bytes(raw[offset + ac * 4:offset + stride], 'big')
            if not size or base + size > 1 << 64:
                raise ValueError('invalid resource bounds')
            windows.append(dict(name=names[i].decode('ascii'), base=hex(base), size=hex(size)))
        return windows

    smmu = [(p, v) for p, v in nodes.items()
            if b'qcom,qsmmu-v500' in v.get('compatible', b'').split(b'\0')
            and 'kgsl' in p]
    if len(smmu) != 1:
        raise ValueError('expected exactly one GPU SMMU')
    return dict(chip_id=hex(chip), gpu='Adreno 610', gpu_windows=resource(path, gpu),
                smmu_windows=resource(*smmu[0]),
                clock_names=gpu.get('clock-names', b'').rstrip(b'\0').decode('ascii').split('\0'),
                hardware_access_performed=False,
                note='FDT inventory only: clocks, ownership, SMMU contexts and GPU execution remain unvalidated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live_fdt', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(profile(args.live_fdt.read_bytes()), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
