import json

data = json.load(open('data/catalog.json'))
print('total kept:', len(data))

bundlish = [e for e in data if len(set(e.get('keys', []))) >= 4]
print(f'entries with 4+ distinct test-type keys (possible bundles): {len(bundlish)}')
for e in bundlish[:15]:
    print('-', e['name'], '|', e.get('keys'))