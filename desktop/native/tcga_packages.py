"""Package the existing public TCGA reference files without changing analyses."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

from data_packages import SCHEMA, digest, identifier, write_package


def export_reference(code, tcga_root, derived_root, cdr_file, output):
    code = identifier(code); cohort_id = 'TCGA-'+code
    tcga_root = Path(tcga_root); derived_root = Path(derived_root); cdr_file = Path(cdr_file)
    with (tcga_root/'summary_table.tsv').open() as stream:
        records = list(csv.DictReader(stream,delimiter='\t'))
    summary = next((row for row in records if row['cohort']==cohort_id),None)
    if not summary: raise ValueError('Cancer not present in the TCGA source summary')
    matrix_root = derived_root/'matrices'/cohort_id
    metadata = json.loads((matrix_root/'metadata.json').read_text())
    if sys.byteorder != 'little' or metadata.get('status')!='ready':
        raise ValueError('TCGA matrix cache must be ready and little-endian')
    files = {}
    for name in ['count_matrix.tsv','col_data.tsv','clinical_data.tsv']:
        files[f'tcga/{cohort_id}/{name}'] = tcga_root/cohort_id/name
    files[f'derived/matrices/{cohort_id}/metadata.json'] = matrix_root/'metadata.json'
    for info in metadata['scales'].values():
        name = identifier(info['file']); path = matrix_root/name
        if path.stat().st_size != metadata['gene_count']*metadata['sample_count']*4:
            raise ValueError('TCGA cached matrix has inconsistent dimensions')
        files[f'derived/matrices/{cohort_id}/{name}'] = path
    files['clinical/TCGA-CDR-SupplementalTableS1.xlsx'] = cdr_file
    checksums = {name:digest(path) for name,path in sorted(files.items())}
    snapshot = hashlib.sha256(json.dumps(checksums,sort_keys=True).encode()).hexdigest()[:16]
    package = {'schema_version':SCHEMA,'cancer_code':code,'snapshot':snapshot,
        'contents':'tcga_reference','tcga_reference_included':True,'releases':[],
        'cohort_summary':summary,'matrix_byte_order':'little','files':checksums,
        'provenance':{'expression_provider':'NCI Genomic Data Commons',
            'expression_url':'https://portal.gdc.cancer.gov/',
            'clinical_url':'https://gdc.cancer.gov/about-data/publications/PanCan-Clinical-2018',
            'clinical_citation':'Liu et al., Cell 2018, doi:10.1016/j.cell.2018.02.052',
            'clinical_resource_scope':'Shared TCGA-CDR reference workbook; this package registers only '+cohort_id,
            'scales':metadata['scales'],'data_release':'not recorded in the source cache metadata',
            'snapshot_definition':'SHA-256 inventory of exact source and prepared matrix files'}}
    return write_package(package,files,output)


def install_reference(package, staging, replace_existing=False):
    from sqlalchemy import delete, select, func
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import Cohort, Sample, GeneIndex, DataSource
    from app.importer import import_samples_for_cohort, ensure_gene_index, import_tcga_cdr, parse_int, clean, TCGA_RNA_SOURCE_ID
    settings=get_settings();code=identifier(package['cancer_code']);cohort_id='TCGA-'+code
    summary=package['cohort_summary']
    if summary['cohort']!=cohort_id or package.get('matrix_byte_order')!='little':
        raise ValueError('Incompatible TCGA reference metadata')
    metadata=json.loads((staging/'derived/matrices'/cohort_id/'metadata.json').read_text())
    for scale in metadata['scales'].values():
        name=identifier(scale['file']);p=staging/'derived/matrices'/cohort_id/name
        if p.stat().st_size!=metadata['gene_count']*metadata['sample_count']*4:
            raise ValueError('Invalid TCGA matrix dimensions')
    cdr_source=staging/'clinical/TCGA-CDR-SupplementalTableS1.xlsx'
    cdr_target=settings.tcga_cdr_path
    if cdr_target.exists() and digest(cdr_target)!=digest(cdr_source):
        raise ValueError('A different TCGA-CDR reference is installed; mixed clinical versions are not supported')
    with SessionLocal() as db:
        from app.models import CancerType
        if db.get(CancerType,code) is None: raise ValueError('Unknown cancer code')
        cohort=db.get(Cohort,cohort_id)
        if cohort and cohort.status!='external_only':
            source=db.get(DataSource,TCGA_RNA_SOURCE_ID)
            old=((source.metadata_json or {}).get('desktop_packages') or {}).get(cohort_id) if source else None
            if old and old['snapshot']==package['snapshot']:
                return {'cancer_code':code,'source':'TCGA','already_installed':True}
            if not replace_existing:
                raise ValueError('Another TCGA reference version is installed. Use the data updater to preserve and replace it.')
            db.execute(delete(Sample).where(Sample.cohort==cohort_id))
            db.execute(delete(GeneIndex).where(GeneIndex.cohort==cohort_id))
        tcga_target=settings.tcga_data_dir/cohort_id
        derived_target=settings.derived_expression_dir/'matrices'/cohort_id
        if replace_existing:
            shutil.rmtree(tcga_target,ignore_errors=True)
            shutil.rmtree(derived_target,ignore_errors=True)
        # Files are installed only after the complete archive passes checksums.
        shutil.copytree(staging/'tcga'/cohort_id,tcga_target,dirs_exist_ok=True)
        shutil.copytree(staging/'derived/matrices'/cohort_id,derived_target,dirs_exist_ok=True)
        cdr_target.parent.mkdir(parents=True,exist_ok=True)
        if not cdr_target.exists():shutil.copy2(cdr_source,cdr_target)
        if cohort is None:cohort=Cohort(id=cohort_id,data_path=str(tcga_target));db.add(cohort)
        cohort.data_path=str(tcga_target);cohort.status=clean(summary.get('status')) or 'ready'
        for key in ['disease_type','primary_site','design_formula']:setattr(cohort,key,clean(summary.get(key)))
        for key in ['n_samples_paired','n_patients_paired','n_primary_tumor','n_solid_normal','n_other_samples','n_genes']:setattr(cohort,key,parse_int(summary.get(key)))
        db.flush()
        import_samples_for_cohort(db,cohort_id,tcga_target)
        ensure_gene_index(db,settings.tcga_data_dir,cohort_id)
        source=db.get(DataSource,TCGA_RNA_SOURCE_ID)
        if source is None:
            source=DataSource(id=TCGA_RNA_SOURCE_ID,label='TCGA RNA-seq cohort data',kind='rna_expression',status='ready');db.add(source)
        source.status='ready';source.source_url='https://portal.gdc.cancer.gov/';source.source_path=str(settings.tcga_data_dir)
        previous=source.metadata_json or {};packages=dict(previous.get('desktop_packages') or {})
        packages[cohort_id]={'snapshot':package['snapshot'],'files':package['files'],'provenance':package['provenance']}
        source.metadata_json={**previous,'desktop_packages':packages}
        db.commit()
        summary_path=settings.tcga_data_dir/'summary_table.tsv'
        old=[]
        if summary_path.exists():
            with summary_path.open() as handle:old=list(csv.DictReader(handle,delimiter='\t'))
        rows=[row for row in old if row['cohort']!=cohort_id]+[summary]
        with summary_path.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(summary),delimiter='\t');writer.writeheader();writer.writerows(rows)
        import_tcga_cdr(db,cdr_target)
        count=db.scalar(select(func.count()).select_from(Sample).where(Sample.cohort==cohort_id))
        return {'cancer_code':code,'source':'TCGA','cohort':cohort_id,'samples':count,'snapshot':package['snapshot']}
