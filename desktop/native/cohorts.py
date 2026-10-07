"""Download a curated cohort directly from its source into the local catalog."""
import json
from pathlib import Path

AVAILABLE = {'cbioportal-skcm-riaz-nivolumab-2017'}


def download(dataset_id):
    if dataset_id not in AVAILABLE:
        raise ValueError('This cohort is not in the desktop download catalog.')
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import CancerType, Cohort, RepositoryDataset, RepositoryRelease
    from app.repository.adapters.cbioportal import build_cbioportal_bundle
    from app.repository.importer import promote_bundle
    settings = get_settings()
    spec_path = settings.cancer_repository_registry_dir / 'studies' / (dataset_id + '.json')
    spec = json.loads(spec_path.read_text())
    if not spec['dataset'].get('redistribution_allowed'):
        raise ValueError('The source does not permit the selected download workflow.')
    with SessionLocal() as db:
        existing = db.get(RepositoryDataset, dataset_id)
        if existing and existing.status == 'available':
            return {'already_installed': True, 'dataset_id': dataset_id}
    pins = json.loads((Path(__file__).parent / 'cohort-pins.json').read_text())
    spec['source']['branch'] = pins[dataset_id]
    staging = settings.cancer_repository_dir / 'staging' / dataset_id
    staging.mkdir(parents=True, exist_ok=True)
    pinned_spec = staging / 'desktop-source-spec.json'
    pinned_spec.write_text(json.dumps(spec, indent=2))
    build_cbioportal_bundle(pinned_spec, staging, force=True)
    with SessionLocal() as db:
        result = promote_bundle(db, staging, settings.cancer_repository_dir, settings.cancer_repository_registry_dir)
        ensure_cancer_cohort(db, dataset_id)
        release = db.get(RepositoryRelease, db.get(RepositoryDataset, dataset_id).active_release_id)
        counts = {'patient_count': release.patient_count, 'sample_count': release.sample_count}
    return {**result, **counts}


def ensure_cancer_cohort(db, dataset_id):
    from app.models import CancerType, Cohort, RepositoryDataset, RepositoryRelease
    dataset = db.get(RepositoryDataset,dataset_id)
    release = db.get(RepositoryRelease,dataset.active_release_id)
    cancer = db.get(CancerType,dataset.cancer_code)
    if db.get(Cohort,cancer.tcga_cohort) is None:
        db.add(Cohort(id=cancer.tcga_cohort,data_path='external_repository',
            disease_type=cancer.name,status='external_only',n_samples_paired=release.sample_count,
            n_patients_paired=release.patient_count,n_genes=release.gene_count))
        db.commit()
