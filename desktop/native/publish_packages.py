"""Build a static download folder from public reference files, without a database."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

from data_packages import SCHEMA, digest, identifier, write_package
from tcga_packages import export_reference


def build(task):
    kind,code,inputs,output=task
    if kind=='tcga_reference':
        result=export_reference(code,*inputs,output)
    else:
        files={};releases=[]
        for root_text,patients,samples in inputs:
            root=Path(root_text);manifest=json.loads((root/'manifest.json').read_text())
            dataset=manifest['dataset'];release=manifest['release']
            if not dataset.get('redistribution_allowed') or dataset.get('visibility','public')!='public' or dataset['source_provider']=='user_upload':
                raise ValueError('Only redistributable public releases may be packaged')
            prefix=f"studies/{identifier(dataset['id'])}/{identifier(release['id'])}"
            for name in set(manifest['checksums'])|{'manifest.json'}:
                source=(root/name).resolve()
                if root.resolve() not in source.parents or source.is_symlink():raise ValueError('Invalid source file')
                if name!='manifest.json' and digest(source)!=manifest['checksums'][name]:raise ValueError('Source checksum mismatch: '+name)
                files[prefix+'/'+name]=source
            releases.append({'dataset_id':dataset['id'],'release_id':release['id'],'bundle_path':prefix,'manifest_sha256':digest(root/'manifest.json'),'source_provider':dataset['source_provider'],'license_id':dataset.get('license_id'),'license_url':dataset.get('license_url'),'patients':patients,'samples':samples})
        checksums={name:digest(value) for name,value in sorted(files.items())}
        snapshot=hashlib.sha256(json.dumps(checksums,sort_keys=True).encode()).hexdigest()[:16]
        package={'schema_version':SCHEMA,'cancer_code':code,'snapshot':snapshot,'contents':'independent_external_study_releases','tcga_reference_included':False,'files':checksums,'releases':releases}
        result=write_package(package,files,output)
    return {'cancer_code':code,'source':kind,'url':result['file'],'bytes':result['bytes'],'sha256':result['sha256'],'snapshot':result['snapshot'],'studies':result['studies']}


def main():
    parser=argparse.ArgumentParser()
    for name in ['tcga','derived','cdr','repository','public-datasets','output']:parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rows=json.loads(args.public_datasets.read_text())['datasets'];tasks=[];excluded=[];external={};names={}
    for row in rows:
        names[row['cancer_code']]=row.get('cancer_name',row['cancer_code'])
        if row['kind']!='external' or not row['redistribution_allowed'] or row['status']!='available':
            excluded.append({'dataset_id':row['id'],'reason':'not eligible for public redistribution'});continue
        root=args.repository/'studies'/identifier(row['id'])/'releases'/identifier(row['active_release_id'])
        if not (root/'manifest.json').exists():raise ValueError('Current public release is missing locally: '+row['id'])
        external.setdefault(row['cancer_code'],[]).append((str(root),row['patient_count'],row['sample_count']))
    for code,roots in sorted(external.items()):
        tasks.append(('external',code,sorted(roots),str(args.output/f'TRACE-{code}-external.tar.gz')))
    for meta in sorted((args.derived/'matrices').glob('TCGA-*/metadata.json')):
        if json.loads(meta.read_text()).get('status')!='ready':continue
        code=meta.parent.name[5:];tasks.append(('tcga_reference',code,[str(args.tcga),str(args.derived),str(args.cdr)],str(args.output/f'TRACE-{code}-TCGA.tar.gz')))
    entries=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(build,task) for task in tasks]):
            entry=future.result();entry['cancer_name']=names.get(entry['cancer_code'],entry['cancer_code']);entries.append(entry)
            print(json.dumps(entry),flush=True)
    catalog={'schema_version':'trace-desktop-download-catalog-v1','minimum_desktop_version':'0.1.3','packages':sorted(entries,key=lambda entry:(entry['cancer_code'],entry['source']))}
    (args.output/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    (args.output/'redistribution-exclusions.json').write_text(json.dumps(excluded,indent=2)+'\n')
    (args.output/'README.txt').write_text('Upload this folder unchanged to an HTTPS host. In TRACE Manage data > Download source, save the public URL of catalog.json. Keep archives and catalog together. TCGA and external studies are separate packages; studies retain their own versions. Source licenses remain in each release manifest. TCGA uses the shared public TCGA-CDR workbook. Exact files are hashed; the upstream GDC release is not recorded in the source cache.\n')
    print(json.dumps({'completed':True,'packages':len(entries),'external_studies':sum(entry['studies'] for entry in entries if entry['source']=='external')}))


if __name__=='__main__':main()
