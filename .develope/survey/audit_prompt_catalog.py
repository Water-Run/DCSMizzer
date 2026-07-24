#!/usr/bin/env python3
"""Machine-checkable structure/coverage/naming audit for PROMPT-SAMPLE catalogs."""
from __future__ import annotations
import re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
ZH = ROOT / 'PROMPT-SAMPLE-zh.adoc'
EN = ROOT / 'PROMPT-SAMPLE.adoc'

AIRCRAFT = {
    'TF-51D': [r'TF-51'], 'Su-25T': [r'Su-25T'],
    'MiG-29A-FF': [r'全模拟 MiG-29A', r'full-fidelity MiG-29A'],
    'M-2000C': [r'M-2000C'], 'JF-17': [r'JF-17'], 'F-16C': [r'F-16C'],
    'F/A-18C': [r'F/A-18'], 'F-14': [r'F-14'], 'F-15E': [r'F-15E'], 'F-4E': [r'F-4E'],
    'A-10C': [r'A-10C'], 'A-10A': [r'A-10A'], 'AV-8B': [r'AV-8B'], 'AJS-37': [r'AJS-37'],
    'Mirage F1': [r'Mirage F1'], 'C-130J': [r'C-130J'], 'F-100D': [r'F-100D'], 'F-5E': [r'F-5E'],
    'MiG-21bis': [r'MiG-21'], 'MiG-19P': [r'MiG-19'], 'MiG-15bis': [r'MiG-15'],
    'MiG-29S': [r'MiG-29S'], 'MiG-29G': [r'MiG-29G'], 'Su-27': [r'Su-27'], 'Su-33': [r'Su-33'],
    'F-15C': [r'F-15C'], 'F-86F': [r'F-86'], 'MB-339': [r'MB-339'], 'L-39': [r'L-39'],
    'C-101': [r'C-101'], 'Yak-52': [r'Yak-52'], 'Christen Eagle II': [r'Christen Eagle'],
    'P-51D': [r'P-51D'], 'P-47D': [r'P-47'], 'Spitfire': [r'Spitfire'], 'Bf 109': [r'Bf 109'],
    'Fw 190 A-8': [r'Fw 190 A-8'], 'Fw 190 D-9': [r'Fw 190 D-9'], 'Mosquito': [r'Mosquito'],
    'I-16': [r'I-16'], 'La-7': [r'La-7'], 'F4U-1D': [r'F4U', r'Corsair'],
    'Ka-50': [r'Ka-50', r'Black Shark'], 'AH-64D': [r'AH-64'], 'Mi-24P': [r'Mi-24'],
    'Mi-8MTV2': [r'Mi-8'], 'UH-1H': [r'UH-1'], 'SA342': [r'SA342', r'Gazelle'],
    'OH-58D': [r'OH-58'], 'CH-47F': [r'CH-47'], 'Supercarrier': [r'Supercarrier'],
    'Combined Arms': [r'Combined Arms'], 'WWII Assets Pack': [r'WWII Assets', r'二战资产'],
    'J-11A': [r'J-11'],
}
MAPS = {
    'Caucasus': [r'Caucasus', r'高加索'], 'Nevada': [r'Nevada', r'Nellis'],
    'Persian Gulf': [r'Persian Gulf', r'波斯湾'], 'Syria': [r'Syria'],
    'Normandy': [r'Normandy'], 'The Channel': [r'The Channel', r'英吉利海峡', r'金字塔之旅', r'Pyramid Tour'],
    'Marianas': [r'Marianas', r'Mariana Islands', r'马里亚纳'],
    'Marianas WWII': [r'Marianas WWII', r'二战马里亚纳'],
    'Cold War Germany': [r'Cold War Germany', r'德国冷战', r'冷战德国'],
    'Kola': [r'Kola', r'科拉'], 'Sinai': [r'Sinai', r'西奈'],
    'South Atlantic': [r'South Atlantic'], 'Afghanistan': [r'Afghanistan'],
    'Iraq': [r'Iraq'], 'East Afghanistan': [r'East Afghanistan'],
    'Southwest Afghanistan': [r'Southwest Afghanistan'], 'Iraq North': [r'Iraq North'],
    'Normandy 2.0': [r'Normandy 2\.0'],
}
SIG_ZH = ['铁幕','金字塔之旅','欢迎来到西奈','夜班清单','虎斑','西方来客']
SIG_EN = ['Iron Curtain','Pyramid Tour','Welcome to Sinai','Night Shift Manifest','Tiger Stripe','Visitors from the West']

def blocks(text):
    return re.findall(r'\[source,text\]\n----\n(.*?)\n----', text, re.S)

def main():
    zh, en = ZH.read_text(), EN.read_text()
    zb, eb = blocks(zh), blocks(en)
    errs = []
    if len(zb) != 144: errs.append(f'ZH blocks {len(zb)} != 144')
    if len(eb) != 144: errs.append(f'EN blocks {len(eb)} != 144')
    if any(len(b.strip()) < 40 for b in zb+eb): errs.append('empty/short source body')
    hz = re.findall(r'^(={2,5}) ', zh, re.M)
    he = re.findall(r'^(={2,5}) ', en, re.M)
    if [len(x) for x in hz] != [len(x) for x in he]:
        errs.append('heading depth sequences differ')
    text = zh + '\n' + en
    for name, pats in AIRCRAFT.items():
        if not any(re.search(p, text, re.I) for p in pats):
            errs.append(f'MISSING aircraft {name}')
    for name, pats in MAPS.items():
        if not any(re.search(p, text, re.I) for p in pats):
            errs.append(f'MISSING map {name}')
    for s in SIG_ZH:
        cnt = sum(1 for i in range(99,144) if f'《{s}》' in zb[i].split('\n')[0])
        if cnt != 1: errs.append(f'signature {s} first-line count {cnt}')
    for s in SIG_EN:
        cnt = sum(1 for i in range(99,144) if s in eb[i].split('\n')[0])
        if cnt != 1: errs.append(f'signature {s} EN first-line count {cnt}')
    iron = zb[101]
    if '全模拟 MiG-29A' not in iron or 'Cold War Germany' not in iron:
        errs.append('Iron Curtain not full-fidelity MiG-29A + CWG')
    if 'F-5E' in iron.split('主座')[1].split('地图')[0]:
        errs.append('Iron Curtain player seat looks like F-5E')
    titles = []
    for i in range(99,144):
        m = re.search(r'《([^》]+)》', zb[i])
        if m: titles.append(m.group(1))
    dups = [t for t,n in Counter(titles).items() if n>1]
    if dups: errs.append(f'duplicate campaign titles {dups}')
    if errs:
        print('FAIL')
        for e in errs: print(' -', e)
        return 1
    print('PASS')
    print(f'blocks ZH/EN 144/144; aircraft {len(AIRCRAFT)}; maps {len(MAPS)}; unique campaign titles {len(set(titles))}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
