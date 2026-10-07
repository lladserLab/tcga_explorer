"""Versioned public cancer packages; releases remain independent studies."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

SCHEMA = 'trace-desktop-cancer-package-v1'
MAX_FILES = 30000
MAX_EXPANDED_BYTES = 20 * 1024**3


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,255}', value):
        raise ValueError('Invalid package identifier')
    return value


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def installed_cancers():
    from app.config import get_settings
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import RepositoryDataset, RepositoryRelease, DataSource
    with SessionLocal() as db:
        rows = db.scalars(select(RepositoryDataset).where(
            RepositoryDataset.visibility == 'public',
            RepositoryDataset.status == 'available',
            RepositoryDataset.redistribution_allowed.is_(True),
        )).all()
        cancers = {}
        inventories = {}
        for row in rows:
            cancers[row.cancer_code] = cancers.get(row.cancer_code, 0) + 1
            release = db.get(RepositoryRelease,row.active_release_id)
            if release:
                root = Path(release.repository_path)
                manifest = json.loads((root/'manifest.json').read_text())
                prefix = f'studies/{row.id}/{release.id}'
                inventory = inventories.setdefault(row.cancer_code,{})
                inventory.update({f'{prefix}/{name}':value for name,value in manifest['checksums'].items()})
                inventory[f'{prefix}/manifest.json'] = digest(root/'manifest.json')
        result = [{'cancer_code':code,'source':'external','studies':count} for code,count in sorted(cancers.items())]
        for entry in result:
            entry['snapshot'] = hashlib.sha256(json.dumps(inventories.get(entry['cancer_code'],{}),sort_keys=True).encode()).hexdigest()[:16]
        from app.models import Cohort
        from app.importer import TCGA_RNA_SOURCE_ID
        source = db.get(DataSource,TCGA_RNA_SOURCE_ID)
        metadata = ((source.metadata_json or {}).get('desktop_packages') or {}) if source else {}
        for cohort in db.scalars(select(Cohort).where(Cohort.status != 'external_only')).all():
            if cohort.id.startswith('TCGA-') and (get_settings().tcga_data_dir/cohort.id/'count_matrix.tsv').is_file():
                result.append({'cancer_code':cohort.id[5:],'source':'tcga_reference','studies':1,'snapshot':metadata.get(cohort.id,{}).get('snapshot')})
        return result


def export_cancer(cancer_code, output):
    from sqlalchemy import select
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import RepositoryDataset, RepositoryRelease
    from app.repository.importer import validate_bundle
    settings = get_settings()
    identifier(cancer_code)
    files = {}
    releases = []
    with SessionLocal() as db:
        datasets = db.scalars(select(RepositoryDataset).where(
            RepositoryDataset.cancer_code == cancer_code,
            RepositoryDataset.visibility == 'public',
            RepositoryDataset.status == 'available',
            RepositoryDataset.redistribution_allowed.is_(True),
        ).order_by(RepositoryDataset.id)).all()
        for dataset in datasets:
            release = db.get(RepositoryRelease, dataset.active_release_id)
            if release is None:
                raise ValueError('An installed study has no active release')
            root = Path(release.repository_path).resolve()
            repository = settings.cancer_repository_dir.resolve()
            if repository not in root.parents:
                raise ValueError('Release is outside the local repository')
            validation = validate_bundle(root)
            if validation['qc']['errors']:
                raise ValueError('The installed release failed integrity validation')
            manifest = validation['manifest']
            if not manifest['dataset'].get('redistribution_allowed'):
                raise ValueError('The release does not allow redistribution')
            prefix = f'studies/{identifier(dataset.id)}/{identifier(release.id)}'
            for relative in sorted(set(manifest['checksums']) | {'manifest.json'}):
                path = root / relative
                if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
                    raise ValueError('Invalid release file')
                files[f'{prefix}/{relative}'] = path
            releases.append({'dataset_id': dataset.id, 'release_id': release.id,
                'bundle_path': prefix, 'manifest_sha256': digest(root / 'manifest.json'),
                'source_provider': dataset.source_provider, 'license_id': dataset.license_id,
                'license_url': dataset.license_url, 'patients': release.patient_count,
                'samples': release.sample_count})
    if not releases:
        raise ValueError('No redistributable public studies are installed for this cancer')
    checksums = {name: digest(path) for name, path in sorted(files.items())}
    snapshot = hashlib.sha256(json.dumps(checksums,sort_keys=True).encode()).hexdigest()[:16]
    package = {'schema_version': SCHEMA, 'cancer_code': cancer_code, 'snapshot': snapshot,
        'contents': 'independent_external_study_releases', 'tcga_reference_included': False,
        'releases': releases, 'files': checksums}
    return write_package(package, files, output)


def write_package(package, files, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the destination, then replace atomically after compression.
    temporary = output.with_name(output.name + '.partial')
    try:
        with temporary.open('wb') as raw, gzip.GzipFile(fileobj=raw,filename='',mode='wb',mtime=0,compresslevel=6) as zipped, tarfile.open(fileobj=zipped,mode='w|') as archive:
            data = json.dumps(package,sort_keys=True,indent=2).encode()
            info = tarfile.TarInfo('package.json');info.size = len(data)
            archive.addfile(info,io.BytesIO(data))
            for name,path in sorted(files.items()):
                info = tarfile.TarInfo(name);info.size = path.stat().st_size
                with path.open('rb') as stream:
                    archive.addfile(info,stream)
        os.replace(temporary,output)
    finally:
        temporary.unlink(missing_ok=True)
    result = {'file': output.name, 'cancer_code': package['cancer_code'], 'snapshot': package['snapshot'],
        'studies': 1 if package['tcga_reference_included'] else len(package['releases']), 'bytes': output.stat().st_size, 'sha256': digest(output),
        'tcga_reference_included': package['tcga_reference_included'], 'releases': package['releases']}
    output.with_name(output.name + '.sha256').write_text(result['sha256']+'  '+output.name+'\n')
    return result


def extract_checked(archive_path, staging, max_bytes=MAX_EXPANDED_BYTES):
    """Reject traversal, Windows aliases, links and oversized archives before use."""
    names = set(); folded_names = set(); total = 0; count = 0
    with tarfile.open(archive_path,'r:gz') as archive:
        for member in archive:
            count += 1
            path = PurePosixPath(member.name)
            if (count > MAX_FILES or '\\' in member.name or ':' in member.name
                    or path.is_absolute() or '..' in path.parts or not path.parts
                    or member.name != path.as_posix()
                    or any(part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for part in path.parts)
                    or any(part.rstrip(' .') != part for part in path.parts)
                    or not member.isfile()):
                raise ValueError('Unsafe or unsupported archive entry')
            folded = member.name.casefold()
            if folded in folded_names:
                raise ValueError('Duplicate archive path')
            names.add(member.name); folded_names.add(folded); total += member.size
            if member.size < 0 or total > max_bytes:
                raise ValueError('Package exceeds the expanded size limit')
            if member.name == 'package.json' and member.size > 2 * 1024**2:
                raise ValueError('Package metadata is too large')
            target = staging.joinpath(*path.parts)
            if staging.resolve() not in target.resolve().parents:
                raise ValueError('Archive path escapes staging directory')
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as source, target.open('wb') as output:
                shutil.copyfileobj(source,output)
    package = json.loads((staging / 'package.json').read_text())
    if package.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported data package version')
    expected = package.get('files')
    if not isinstance(expected,dict) or set(expected) != names - {'package.json'}:
        raise ValueError('Package file inventory does not match the archive')
    if 'snapshot' in package and package['snapshot'] != hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Package snapshot does not match its file inventory')
    for name,expected_hash in expected.items():
        if digest(staging / name) != expected_hash:
            raise ValueError('Package checksum mismatch: '+name)
    return package


def import_package(archive_path, update=False):
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import RepositoryRelease
    from app.repository.importer import preflight_bundle_promotion, promote_bundle
    from cohorts import ensure_cancer_cohort
    settings = get_settings()
    staging_root = settings.cancer_repository_dir / 'staging'
    staging_root.mkdir(parents=True,exist_ok=True)
    # Windows' temporary folder avoids adding long study IDs to the already
    # deep AppData/workspace/cohorts/staging path during archive extraction.
    with tempfile.TemporaryDirectory(prefix='tr-',dir=None if os.name=='nt' else staging_root) as folder:
        staging = Path(folder)
        package = extract_checked(archive_path,staging)
        if package.get('contents') == 'tcga_reference':
            if update:
                from reference_updates import update_reference
                return update_reference(package,staging)
            from tcga_packages import install_reference
            return install_reference(package,staging)
        code = identifier(package['cancer_code'])
        releases = package.get('releases')
        if not isinstance(releases,list) or not releases:
            raise ValueError('No study releases in the package')
        bundles = [];ids = set()
        for entry in releases:
            dataset_id = identifier(entry['dataset_id']);release_id = identifier(entry['release_id'])
            if release_id in ids or entry['bundle_path'] != f'studies/{dataset_id}/{release_id}':
                raise ValueError('Invalid or duplicate study release')
            ids.add(release_id)
            bundle = staging / entry['bundle_path']
            if digest(bundle / 'manifest.json') != entry['manifest_sha256']:
                raise ValueError('Release manifest hash mismatch')
            validation = preflight_bundle_promotion(bundle,settings.cancer_repository_registry_dir)
            manifest = validation['manifest']
            if (manifest['dataset']['id'] != dataset_id or manifest['release']['id'] != release_id
                    or manifest['dataset']['cancer_code'] != code
                    or not manifest['dataset'].get('redistribution_allowed')
                    or manifest['dataset'].get('visibility','public') != 'public'
                    or manifest['dataset']['source_provider'] == 'user_upload'):
                raise ValueError('Incompatible or non-public study in package')
            bundles.append((bundle,release_id,validation))
        results = []
        with SessionLocal() as db:
            for bundle,release_id,validation in bundles:
                existing = db.get(RepositoryRelease,release_id)
                if existing:
                    from app.repository.storage import canonical_json_sha256
                    if existing.manifest_hash != canonical_json_sha256(validation['manifest']):
                        raise ValueError('Installed immutable release has different content')
                    results.append({'release_id':release_id,'already_installed':True})
                    continue
                result = promote_bundle(db,bundle,settings.cancer_repository_dir,settings.cancer_repository_registry_dir)
                ensure_cancer_cohort(db,result['dataset_id'])
                results.append(result)
        return {'cancer_code':code,'studies':len(results),'releases':results}
