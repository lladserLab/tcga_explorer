"""Entrypoint for the bundled Python/R engine (no container or public server)."""
import os
from pathlib import Path
import sys


def configure():
    root = Path(__file__).resolve().parent
    home = Path(os.environ['TRACE_DESKTOP_HOME']).resolve()
    port = int(os.environ.get('TRACE_DESKTOP_PORT', '3100'))
    home.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'backend'))
    values = {
        'LOCAL_DESKTOP_MODE': 'true',
        'DATABASE_URL': 'sqlite:///' + (home / 'trace.sqlite').as_posix(),
        'DATABASE_SCHEMA_MANAGEMENT_ENABLED': 'true',
        'CANCER_REPOSITORY_REGISTRY_DIR': str(root / 'repository_registry'),
        'R_SCRIPT_PATH': str(root / 'backend/scripts/km_analysis.R'),
        'MAXSTAT_SCRIPT_PATH': str(root / 'backend/scripts/maxstat_cutpoint.R'),
        'PANCANCER_SCRIPT_PATH': str(root / 'backend/scripts/pancancer_cox_scan.R'),
        'GSEA_GENE_SET_DIR': str(root / 'backend/gene_sets'),
        'PUBLICATION_BENCHMARK_DIR': str(root / 'empty_benchmark'),
        'BOOTSTRAP_ON_STARTUP': 'false', 'PRELOAD_CACHE_ON_STARTUP': 'false',
        'PRELOAD_CACHE_STRICT': 'false', 'PRELOAD_GDC_EXPRESSION_MATRICES_ON_STARTUP': 'false',
        'PUBLIC_BASE_URL': f'http://127.0.0.1:{port}/tcga_explorer',
        'PUBLIC_PATH_PREFIX': '', 'ALLOWED_HOSTS': '127.0.0.1,localhost,testserver',
        'CORS_ORIGINS': f'http://127.0.0.1:{port}',
        'MCP_ALLOWED_HOSTS': f'127.0.0.1,127.0.0.1:{port},localhost,localhost:*',
        'MCP_ALLOWED_ORIGINS': f'http://127.0.0.1:{port}',
        'COMPUTE_GLOBAL_CONCURRENCY': '1', 'USER_DATASET_MAX_ACTIVE_PER_CLIENT': '1000',
        'ATTESTATION_PRIVATE_KEY_PATH': str(home / 'keys/ed25519-private.pem'),
        'ATTESTATION_ISSUER': 'trace-desktop-local',
        'APP_RELEASE_REF': 'desktop-native-prototype',
    }
    folders = {
        'TCGA_DATA_DIR': 'tcga', 'CANCER_REPOSITORY_DIR': 'cohorts',
        'USER_DATASET_DIR': 'projects', 'ARTIFACT_DIR': 'results',
        'DERIVED_EXPRESSION_DIR': 'derived', 'JCGA_DATA_DIR': 'jcga',
        'TCGA_SYNC_STATE_DIR': 'sync/tcga', 'CLINICAL_SYNC_STATE_DIR': 'sync/clinical',
    }
    for key, folder in folders.items():
        location = home / folder
        location.mkdir(parents=True, exist_ok=True)
        values[key] = str(location)
    values['TCGA_CDR_PATH'] = str(home / 'clinical/TCGA-CDR-SupplementalTableS1.xlsx')
    os.environ.update(values)
    os.environ['R_HOME'] = str(root / 'R')
    os.environ['R_LIBS_USER'] = str(root / 'R/library')
    os.environ['PATH'] = str(root / 'R/bin/x64') + os.pathsep + os.environ.get('PATH', '')
    return root, port


if __name__ == '__main__':
    root, port = configure()
    from app.database import init_db
    init_db()
    # Register taxonomy before first-time downloads or package imports too.
    import initialize
    initialize.initialize()
    if '--data-idle' in sys.argv:
        from reference_updates import require_idle
        require_idle()
        print('{"idle":true}')
        raise SystemExit(0)
    if any(flag in sys.argv for flag in ('--package-export','--package-import','--package-update','--package-list','--tcga-export-source','--package-export-tcga')):
        import json
        from data_packages import export_cancer, import_package, installed_cancers
        if '--tcga-export-source' in sys.argv:
            from tcga_packages import export_reference
            offset=sys.argv.index('--tcga-export-source')
            result=export_reference(*sys.argv[offset+1:offset+6])
        elif '--package-export-tcga' in sys.argv:
            from tcga_packages import export_reference
            from app.config import get_settings
            settings=get_settings();offset=sys.argv.index('--package-export-tcga')
            result=export_reference(sys.argv[offset+1],settings.tcga_data_dir,settings.derived_expression_dir,settings.tcga_cdr_path,sys.argv[offset+2])
        elif '--package-export' in sys.argv:
            offset = sys.argv.index('--package-export')
            result = export_cancer(sys.argv[offset+1],sys.argv[offset+2])
        elif '--package-import' in sys.argv:
            result = import_package(Path(sys.argv[sys.argv.index('--package-import')+1]))
        elif '--package-update' in sys.argv:
            result = import_package(Path(sys.argv[sys.argv.index('--package-update')+1]),update=True)
        else:
            result = installed_cancers()
        print(json.dumps(result))
        raise SystemExit(0)
    if '--download' in sys.argv:
        import json
        from cohorts import download
        print(json.dumps(download(sys.argv[sys.argv.index('--download') + 1])))
        raise SystemExit(0)
    if '--worker' in sys.argv:
        from app.worker import main
        raise SystemExit(main())
    import uvicorn
    from app.main import app
    from serving import create_desktop_app
    wrapper = create_desktop_app(app, root / 'frontend')
    uvicorn.run(wrapper, host='127.0.0.1', port=port, access_log=False)
