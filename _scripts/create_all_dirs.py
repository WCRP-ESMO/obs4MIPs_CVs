import glob
import os
import json

for file in glob.glob('obs4MIPs-cmor-tables/obs4MIPs_*'):
    fname = file.split('/')[-1].replace('obs4MIPs_','').replace('.json','')
    if not os.path.isfile(f'obs4MIPs_CVs/{fname}/000_context.jsonld'):
        continue

    with open(file) as f:
        refs = json.load(f)[fname]

    if isinstance(refs, dict):
        refs = list(refs.keys())

    oldkeys = [k.split('/')[-1].replace('.json','') for k in glob.glob(f'obs4MIPs_CVs/{fname}/*.json') if 'context' not in k]

    remove_keys = [ok for ok in oldkeys if ok not in refs]
    print(f'{fname} - Keys to remove: {remove_keys}')

    for key in refs:
        if ' ' in key:
            print(f'Skipped {key}')
            continue
        with open(f'obs4MIPs_CVs/{fname}/{key}.json','w') as g:
            g.write(json.dumps({
                    "@context": "000_context.jsonld",
                    "id": key.lower(),
                    "type": fname
                }
            ))