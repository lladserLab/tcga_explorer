# Reporte detallado de la carpeta TCGA en /mnt/data1

- Ruta inspeccionada: `/mnt/data1/Andres/TCGA`
- Reporte generado: `2026-04-25 18:34:02 UTC`
- Destino del reporte: `/mnt/data2/tcga_explorer/TCGA_data_report.md`

## Resumen ejecutivo

La carpeta contiene un repositorio pan-cancer TCGA con datos RNA-seq, clinicos, objetos DESeq2 sin ejecutar DESeq(), datos proteomicos RPPA, caches de descarga GDC/RPPA, logs y una capa separada de curacion de cohortes tratadas externas. El volumen observado es de **48.8 GB**, repartido en **19,804 archivos** y **19,648 subdirectorios**.

- Cohortes TCGA procesadas en raiz: **33**.
- RNA-seq emparejado con clinica: **11,505 muestras** y **10,517 pacientes** sumados por cohorte.
- Composicion de muestras RNA: **10,157 primarias**, **740 normales solidas**, **608 otras**.
- Genes por matriz de conteos: **59,427** en todas las cohortes validadas.
- Estado del backbone RNA/clinico: `success: 33` en `summary_table.tsv`; validacion local: `pass: 33` en `tcga_validation_summary.tsv`.
- RPPA: `no_rppa_category: 1, success: 32`; **7,906 muestras RPPA**, **7,827 pacientes RPPA** y **7,534 pacientes con overlap RNA local** sumados por cohorte.
- Matriz RPPA por `peptide_target`: escrita en **24** cohortes; omitida en **8** por targets duplicados; **TCGA-LAML** no tiene categoria RPPA disponible en GDC segun los archivos locales.
- Capa `treated/`: registro y manifiestos de cohortes externas tratadas; no contiene FASTQ ni matrices tratadas descargadas.

## Estructura observada

La estructura principal tiene cuatro capas:

1. `TCGA-*`: una carpeta por cohorte con outputs procesados y listos para analisis.
2. `gdc_cache/`: cache crudo de GDC/TCGAbiolinks para RNA-seq STAR counts.
3. `rppa_cache/`: cache crudo de GDC/TCGAbiolinks para RPPA.
4. `treated/`: curacion, colas y manifiestos para cohortes externas de pacientes tratados.

| ruta | tipo | archivos | subdirs | tamano |
| --- | --- | --- | --- | --- |
| gdc_cache | directorio | 11505 | 11604 | 45.4 GB |
| rppa_cache | directorio | 7906 | 8002 | 166 MB |
| gdc-client_2.3_Ubuntu_x64.zip | archivo | 1 | 0 | 21.1 MB |
| gdc-client_2.3_Ubuntu_x64-py3.8-ubuntu-20.04.zip | archivo | 1 | 0 | 21.0 MB |
| pipeline_resume_20260420_1830.log | archivo | 1 | 0 | 15.5 MB |
| pipeline_stdout.log | archivo | 1 | 0 | 6.75 MB |
| tcga_rppa_panel.tsv | archivo | 1 | 0 | 793 KB |
| rppa_panel_examples | directorio | 32 | 0 | 703 KB |
| treated | directorio | 20 | 3 | 252 KB |
| logs | directorio | 33 | 0 | 186 KB |
| download_pipeline.R | archivo | 1 | 0 | 43.0 KB |
| results.rds | archivo | 1 | 0 | 18.1 KB |
| treated_bulk_rnaseq_candidates.md | archivo | 1 | 0 | 13.0 KB |
| download_tcga_rppa.R | archivo | 1 | 0 | 11.6 KB |
| tcga_rppa_download_summary.tsv | archivo | 1 | 0 | 10.3 KB |
| CLAUDE.md | archivo | 1 | 0 | 9.91 KB |
| MANIFEST.txt | archivo | 1 | 0 | 7.76 KB |
| summary_table.tsv | archivo | 1 | 0 | 7.47 KB |
| treated_bulk_rnaseq_candidates.tsv | archivo | 1 | 0 | 6.90 KB |
| validate_tcga_outputs.R | archivo | 1 | 0 | 6.83 KB |
| TCGA_progress_summary.md | archivo | 1 | 0 | 6.66 KB |
| df.rds | archivo | 1 | 0 | 6.19 KB |
| survey_tcga_rppa.R | archivo | 1 | 0 | 4.69 KB |
| extract_tcga_rppa_panel.R | archivo | 1 | 0 | 4.00 KB |
| tcga_rppa_panel_targets.txt | archivo | 1 | 0 | 3.72 KB |
| tcga_rppa_availability.tsv | archivo | 1 | 0 | 2.73 KB |
| tcga_validation_summary.tsv | archivo | 1 | 0 | 2.47 KB |
| .claude | directorio | 1 | 0 | 501 B |
| pipeline_resume_20260420_1829.log | archivo | 1 | 0 | 0 B |

## Archivos por extension

| extension | archivos | tamano |
| --- | --- | --- |
| .tsv | 19712 | 47.4 GB |
| .log | 36 | 22.5 MB |
| .rds | 35 | 1.28 GB |
| .r | 8 | 84.6 KB |
| .txt | 5 | 76.5 KB |
| .md | 4 | 34.5 KB |
| .zip | 2 | 42.1 MB |
| .json | 1 | 501 B |
| [sin extension] | 1 | 1 B |

## Backbone TCGA RNA-seq y clinico

Cada carpeta `TCGA-XXX/` contiene la capa procesada del cohort. Los archivos principales son:

- `count_matrix.tsv`: matriz de conteos RNA-seq STAR, filas = simbolos de genes y columnas = barcodes TCGA completos.
- `clinical_data.tsv`: clinica de GDC a nivel paciente, filtrada a pacientes con muestra RNA local.
- `col_data.tsv`: metadatos de muestra para DESeq2, con `sample_type` y campos clinicos fusionados.
- `dds.rds`: objeto `DESeqDataSet` guardado, sin haber corrido `DESeq()`. No contiene resultados de expresion diferencial.
- Archivos `rppa_*`: matrices y metadatos de proteomica RPPA cuando hay datos disponibles.

Diseno DESeq2 observado: `~1: 6, ~sample_type: 27`. Las cohortes con un solo tipo de muestra usan `~1`; las cohortes con al menos dos niveles de `sample_type` usan `~sample_type`.

### Presencia de archivos procesados por cohorte

| archivo | cohortes |
| --- | --- |
| clinical_data.tsv | 33 |
| col_data.tsv | 33 |
| count_matrix.tsv | 33 |
| dds.rds | 33 |
| rppa_expression_by_target.tsv | 24 |
| rppa_expression_matrix.tsv | 32 |
| rppa_feature_metadata.tsv | 32 |
| rppa_manifest.tsv | 32 |
| rppa_sample_metadata.tsv | 32 |

### Cohortes con mas muestras RNA

| cohorte | muestras_RNA | pacientes | primario | normal | otros |
| --- | --- | --- | --- | --- | --- |
| TCGA-BRCA | 1231 | 1095 | 1111 | 113 | 7 |
| TCGA-KIRC | 614 | 533 | 541 | 72 | 1 |
| TCGA-LUAD | 601 | 518 | 540 | 59 | 2 |
| TCGA-UCEC | 589 | 557 | 553 | 35 | 1 |
| TCGA-THCA | 572 | 505 | 505 | 59 | 8 |
| TCGA-HNSC | 566 | 521 | 520 | 44 | 2 |
| TCGA-LUSC | 562 | 501 | 511 | 51 | 0 |
| TCGA-PRAD | 554 | 497 | 501 | 52 | 1 |
| TCGA-LGG | 534 | 516 | 516 | 0 | 18 |
| TCGA-COAD | 524 | 458 | 481 | 41 | 2 |

## Tabla detallada por cohorte

| cohorte | RNA muestras | RNA pacientes | primario | normal | otros | diseno | validacion | RPPA muestras | RPPA pacientes | overlap RNA | features RPPA | matriz target | dir procesado | cache GDC | cache RPPA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TCGA-ACC | 79 | 79 | 79 | 0 | 0 | ~1 | pass | 46 | 46 | 46 | 487 | si | 21.8 MB | 318 MB | 968 KB |
| TCGA-BLCA | 431 | 406 | 412 | 19 | 0 | ~sample_type | pass | 343 | 343 | 338 | 727 | no, targets duplicados | 117 MB | 1.70 GB | 7.24 MB |
| TCGA-BRCA | 1231 | 1095 | 1111 | 113 | 7 | ~sample_type | pass | 919 | 881 | 878 | 487 | si | 349 MB | 4.86 GB | 19.6 MB |
| TCGA-CESC | 309 | 304 | 304 | 3 | 2 | ~sample_type | pass | 172 | 172 | 170 | 487 | si | 86.0 MB | 1.22 GB | 3.62 MB |
| TCGA-CHOL | 44 | 36 | 35 | 9 | 0 | ~sample_type | pass | 30 | 30 | 30 | 487 | si | 13.0 MB | 177 MB | 642 KB |
| TCGA-COAD | 524 | 458 | 481 | 41 | 2 | ~sample_type | pass | 363 | 360 | 359 | 727 | no, targets duplicados | 135 MB | 2.06 GB | 7.82 MB |
| TCGA-DLBC | 48 | 48 | 48 | 0 | 0 | ~1 | pass | 33 | 33 | 33 | 487 | si | 13.9 MB | 193 MB | 709 KB |
| TCGA-ESCA | 198 | 184 | 184 | 13 | 1 | ~sample_type | pass | 126 | 126 | 125 | 487 | si | 59.7 MB | 804 MB | 2.66 MB |
| TCGA-GBM | 391 | 293 | 372 | 5 | 14 | ~sample_type | pass | 243 | 237 | 132 | 1447 | no, targets duplicados | 115 MB | 1.54 GB | 4.77 MB |
| TCGA-HNSC | 566 | 521 | 520 | 44 | 2 | ~sample_type | pass | 354 | 354 | 348 | 967 | no, targets duplicados | 152 MB | 2.23 GB | 7.35 MB |
| TCGA-KICH | 91 | 66 | 66 | 25 | 0 | ~sample_type | pass | 63 | 63 | 63 | 487 | si | 26.2 MB | 368 MB | 1.32 MB |
| TCGA-KIRC | 614 | 533 | 541 | 72 | 1 | ~sample_type | pass | 478 | 478 | 475 | 487 | si | 173 MB | 2.43 GB | 7.72 MB |
| TCGA-KIRP | 323 | 290 | 290 | 32 | 1 | ~sample_type | pass | 216 | 215 | 214 | 487 | si | 89.0 MB | 1.27 GB | 4.60 MB |
| TCGA-LAML | 151 | 151 | 0 | 0 | 151 | ~1 | pass | 0 | 0 | 0 | 0 | sin RPPA | 42.3 MB | 610 MB | 0 B |
| TCGA-LGG | 534 | 516 | 516 | 0 | 18 | ~sample_type | pass | 435 | 430 | 430 | 487 | si | 152 MB | 2.11 GB | 9.13 MB |
| TCGA-LIHC | 424 | 371 | 371 | 50 | 3 | ~sample_type | pass | 184 | 184 | 181 | 487 | si | 110 MB | 1.66 GB | 3.87 MB |
| TCGA-LUAD | 601 | 518 | 540 | 59 | 2 | ~sample_type | pass | 365 | 365 | 362 | 487 | si | 168 MB | 2.37 GB | 8.15 MB |
| TCGA-LUSC | 562 | 501 | 511 | 51 | 0 | ~sample_type | pass | 328 | 328 | 325 | 487 | si | 159 MB | 2.22 GB | 7.34 MB |
| TCGA-MESO | 87 | 87 | 87 | 0 | 0 | ~1 | pass | 62 | 62 | 62 | 487 | si | 24.7 MB | 351 MB | 1.33 MB |
| TCGA-OV | 434 | 427 | 426 | 0 | 8 | ~sample_type | pass | 432 | 422 | 306 | 727 | no, targets duplicados | 128 MB | 1.72 GB | 9.42 MB |
| TCGA-PAAD | 183 | 178 | 178 | 4 | 1 | ~sample_type | pass | 120 | 120 | 113 | 487 | si | 51.3 MB | 740 MB | 2.54 MB |
| TCGA-PCPG | 187 | 179 | 179 | 3 | 5 | ~sample_type | pass | 82 | 80 | 80 | 487 | si | 50.6 MB | 754 MB | 1.72 MB |
| TCGA-PRAD | 554 | 497 | 501 | 52 | 1 | ~sample_type | pass | 352 | 352 | 351 | 487 | si | 151 MB | 2.19 GB | 7.40 MB |
| TCGA-READ | 177 | 167 | 166 | 10 | 1 | ~sample_type | pass | 132 | 131 | 129 | 727 | no, targets duplicados | 46.5 MB | 713 MB | 2.72 MB |
| TCGA-SARC | 265 | 259 | 259 | 2 | 4 | ~sample_type | pass | 226 | 223 | 221 | 487 | si | 73.4 MB | 1.04 GB | 4.76 MB |
| TCGA-SKCM | 473 | 469 | 103 | 1 | 369 | ~sample_type | pass | 352 | 350 | 349 | 487 | si | 130 MB | 1.86 GB | 7.37 MB |
| TCGA-STAD | 448 | 415 | 412 | 36 | 0 | ~sample_type | pass | 357 | 357 | 336 | 727 | no, targets duplicados | 133 MB | 1.77 GB | 7.52 MB |
| TCGA-TGCT | 156 | 150 | 150 | 0 | 6 | ~sample_type | pass | 122 | 118 | 118 | 487 | si | 45.3 MB | 631 MB | 2.71 MB |
| TCGA-THCA | 572 | 505 | 505 | 59 | 8 | ~sample_type | pass | 381 | 377 | 375 | 487 | si | 159 MB | 2.26 GB | 8.01 MB |
| TCGA-THYM | 122 | 120 | 120 | 2 | 0 | ~sample_type | pass | 90 | 90 | 87 | 487 | si | 35.2 MB | 493 MB | 1.93 MB |
| TCGA-UCEC | 589 | 557 | 553 | 35 | 1 | ~sample_type | pass | 440 | 440 | 438 | 727 | no, targets duplicados | 155 MB | 2.32 GB | 9.39 MB |
| TCGA-UCS | 57 | 57 | 57 | 0 | 0 | ~1 | pass | 48 | 48 | 48 | 487 | si | 17.6 MB | 231 MB | 1.01 MB |
| TCGA-UVM | 80 | 80 | 80 | 0 | 0 | ~1 | pass | 12 | 12 | 12 | 487 | si | 21.1 MB | 322 MB | 247 KB |

## RPPA proteomico

La capa RPPA fue descargada desde GDC como `Proteome Profiling` / `Protein Expression Quantification` con estrategia `Reverse Phase Protein Array`. Localmente se importo a matrices por cohorte y a metadatos de features/muestras.

- `rppa_expression_matrix.tsv`: filas = features de anticuerpo/plataforma; columnas = muestras RPPA.
- `rppa_feature_metadata.tsv`: anotaciones de feature, incluyendo `AGID`, `lab_id`, `catalog_number`, `set_id` y `peptide_target`.
- `rppa_sample_metadata.tsv`: barcode RPPA, paciente derivado, archivo GDC y flag de overlap con RNA local.
- `rppa_manifest.tsv`: metadata de GDC usada para descargar/importar.
- `rppa_expression_by_target.tsv`: solo existe cuando cada `peptide_target` mapea a una unica feature en la cohorte. En paneles mixtos no se colapsa silenciosamente.

Cohortes con `rppa_expression_by_target.tsv` omitido por targets duplicados: `TCGA-BLCA`, `TCGA-COAD`, `TCGA-GBM`, `TCGA-HNSC`, `TCGA-OV`, `TCGA-READ`, `TCGA-STAD`, `TCGA-UCEC`. `TCGA-LAML` no tiene RPPA descargable en esta estructura.

## Caches de descarga

`gdc_cache/` ocupa la mayor parte del disco. Contiene los TSV crudos `*.rna_seq.augmented_star_gene_counts.tsv` producidos por GDC para `Transcriptome Profiling / Gene Expression Quantification / STAR - Counts`. Cada cohorte tiene una jerarquia `TCGA-XXX/Transcriptome_Profiling/Gene_Expression_Quantification/<uuid>/<archivo>.tsv`.

Mayores caches GDC:

| cohorte | tamano_cache_gdc | archivos | raw_count_files |
| --- | --- | --- | --- |
| TCGA-BRCA | 4.86 GB | 1231 | 1231 |
| TCGA-KIRC | 2.43 GB | 614 | 614 |
| TCGA-LUAD | 2.37 GB | 601 | 601 |
| TCGA-UCEC | 2.32 GB | 589 | 589 |
| TCGA-THCA | 2.26 GB | 572 | 572 |
| TCGA-HNSC | 2.23 GB | 566 | 566 |
| TCGA-LUSC | 2.22 GB | 562 | 562 |
| TCGA-PRAD | 2.19 GB | 554 | 554 |
| TCGA-LGG | 2.11 GB | 534 | 534 |
| TCGA-COAD | 2.06 GB | 524 | 524 |

`rppa_cache/` contiene los TSV crudos de RPPA por UUID de archivo GDC. Su tamano total observado es relativamente pequeno frente al cache RNA.

## Uso de espacio

Carpetas procesadas `TCGA-*` mas grandes:

| cohorte | tamano |
| --- | --- |
| TCGA-BRCA | 349 MB |
| TCGA-KIRC | 173 MB |
| TCGA-LUAD | 168 MB |
| TCGA-LUSC | 159 MB |
| TCGA-THCA | 159 MB |
| TCGA-UCEC | 155 MB |
| TCGA-LGG | 152 MB |
| TCGA-HNSC | 152 MB |
| TCGA-PRAD | 151 MB |
| TCGA-COAD | 135 MB |

Archivos individuales mas grandes:

| archivo | tamano |
| --- | --- |
| TCGA-BRCA/count_matrix.tsv | 192 MB |
| TCGA-BRCA/dds.rds | 144 MB |
| TCGA-KIRC/count_matrix.tsv | 96.1 MB |
| TCGA-LUAD/count_matrix.tsv | 93.1 MB |
| TCGA-THCA/count_matrix.tsv | 89.3 MB |
| TCGA-UCEC/count_matrix.tsv | 88.2 MB |
| TCGA-LUSC/count_matrix.tsv | 88.0 MB |
| TCGA-HNSC/count_matrix.tsv | 86.6 MB |
| TCGA-PRAD/count_matrix.tsv | 86.0 MB |
| TCGA-LGG/count_matrix.tsv | 84.0 MB |
| TCGA-COAD/count_matrix.tsv | 78.8 MB |
| TCGA-SKCM/count_matrix.tsv | 72.7 MB |
| TCGA-KIRC/dds.rds | 72.5 MB |
| TCGA-STAD/count_matrix.tsv | 71.8 MB |
| TCGA-OV/count_matrix.tsv | 69.3 MB |
| TCGA-LUAD/dds.rds | 68.5 MB |
| TCGA-BLCA/count_matrix.tsv | 66.1 MB |
| TCGA-LUSC/dds.rds | 65.8 MB |
| TCGA-THCA/dds.rds | 63.5 MB |
| TCGA-LIHC/count_matrix.tsv | 63.2 MB |

## Esquema de archivos clave

Ejemplo tomado de `TCGA-BRCA`, que es la cohorte procesada mas grande. `filas_datos` excluye la cabecera.

| archivo | columnas | filas_datos | primeras_columnas |
| --- | --- | --- | --- |
| TCGA-BRCA/count_matrix.tsv | 1232 | 59427 | [rowname], TCGA-BH-A18H-01A-11R-A12D-07, TCGA-E2-A14P-01A-31R-A12D-07, TCGA-AN-A04A-01A-21R-A034-07, TCGA-5L-AAT1-01A-12R-A41B-07, TCGA-GI-A2C8-11A-22R-A16F-07, TCGA-AQ-A0Y5-01A-11R-A14M-07, TCGA-A8-A07I-01A-11R-A00Z-07, TCGA-E9-A1R4-01A-21R-A14D-07, TCGA-AC-A8OP-01A-11R-A36F-07 |
| TCGA-BRCA/col_data.tsv | 150 | 1231 | [rowname], patient_id, barcode, patient, sample, shortLetterCode, definition, sample_submitter_id, tumor_descriptor, sample_id |
| TCGA-BRCA/clinical_data.tsv | 101 | 1095 | project, submitter_id, synchronous_malignancy, ajcc_pathologic_stage, days_to_diagnosis, laterality, created_datetime, last_known_disease_status, tissue_or_organ_of_origin, age_at_diagnosis |
| TCGA-BRCA/rppa_expression_matrix.tsv | 919 | 487 | TCGA-E2-A14P-01A-21-A13E-20, TCGA-AN-A04A-01A-11-A13A-20, TCGA-AO-A0J5-01A-21-A13A-20, TCGA-AR-A2LR-01A-21-A24A-20, TCGA-C8-A1HI-01A-21-A17J-20, TCGA-A2-A0YM-01A-21-A13D-20, TCGA-AO-A1KQ-01A-21-A17I-20, TCGA-D8-A1JP-01A-21-A17J-20, TCGA-AO-A03O-01A-31-A13A-20, TCGA-AQ-A7U7-01A-11-A43F-20 |
| TCGA-BRCA/rppa_feature_metadata.tsv | 6 | 487 | feature_id, AGID, lab_id, catalog_number, set_id, peptide_target |
| TCGA-BRCA/rppa_sample_metadata.tsv | 9 | 919 | rppa_barcode, sample_barcode, patient_id, file_id, file_name, sample_type, data_format, platform, patient_in_local_rna |
| TCGA-BRCA/rppa_manifest.tsv | 24 | 919 | id, data_format, cases, access, file_name, submitter_id, data_category, type, platform, file_size |

Cabeceras de tablas raiz relevantes:

- `summary_table.tsv`: 13 columnas: `cohort, disease_type, primary_site, n_samples_downloaded, n_samples_paired, n_patients_paired, n_primary_tumor, n_solid_normal, n_other_samples, n_genes, design_formula, status, notes`
- `tcga_rppa_download_summary.tsv`: 13 columnas: `cohort, status, rppa_files, rppa_samples, rppa_patients, rppa_features, rppa_peptide_targets, overlapping_rna_patients, matrix_path, feature_metadata_path, sample_metadata_path, manifest_path, notes`
- `tcga_validation_summary.tsv`: 15 columnas: `cohort, status, missing_files, count_matrix_parseable, count_matrix_genes, count_matrix_samples, col_data_parseable, col_data_rows, clinical_data_parseable, clinical_rows, dds_loadable, sample_names_match, sample_type_present, summary_consistent, issues`

## Capa treated

La carpeta `treated/` no es un cache de datos descargados. Es una capa de planificacion para extender el backbone no tratado de TCGA con cohortes bulk RNA-seq de pacientes tratados, separando cohortes abiertas de cohortes con acceso controlado. Los focos operativos locales son `SKCM`, `BRCA` y `KIRC`; los manifiestos concretos existentes se concentran en BRCA y KIRC.

| archivo | tamano | filas_datos |
| --- | --- | --- |
| treated/README.md | 4.91 KB |  |
| treated/build_download_lists.R | 2.73 KB |  |
| treated/build_priority_manifests.R | 9.07 KB |  |
| treated/build_queues.R | 2.67 KB |  |
| treated/clinical_trial_table.tsv | 12.3 KB | 27 |
| treated/cohort_summary.tsv | 4.62 KB | 18 |
| treated/controlled_access_queue.tsv | 1.55 KB | 5 |
| treated/manifests/.gitkeep | 1 B |  |
| treated/manifests/brca_priority_download_manifest.tsv | 2.14 KB | 5 |
| treated/manifests/download_lists/GSE159448_fastq_urls.txt | 1.95 KB | 23 |
| treated/manifests/download_lists/GSE243375_fastq_urls.txt | 46.5 KB | 573 |
| treated/manifests/download_lists/PRJNA995589_fastq_urls.txt | 16.5 KB | 203 |
| treated/manifests/download_lists/brca_download_list_index.tsv | 467 B | 3 |
| treated/manifests/kirc_priority_download_manifest.tsv | 3.52 KB | 8 |
| treated/manifests/manifest_index.tsv | 445 B | 2 |
| treated/manifests/runinfo/TCGA_BRCA_GSE159448_runinfo.tsv | 3.98 KB | 12 |
| treated/manifests/runinfo/TCGA_BRCA_GSE243375_runinfo.tsv | 91.8 KB | 287 |
| treated/manifests/runinfo/TCGA_BRCA_PRJNA995589_runinfo.tsv | 32.7 KB | 102 |
| treated/open_priority_queue.tsv | 2.70 KB | 11 |
| treated/registry.tsv | 11.4 KB | 18 |

## Scripts y documentacion local

- `download_pipeline.R`: descarga y procesa RNA-seq STAR counts y clinica para las 33 cohortes usando GDC/TCGAbiolinks; es resumible.
- `validate_tcga_outputs.R`: valida existencia y parseabilidad de archivos, alineacion entre `count_matrix.tsv` y `col_data.tsv`, carga de `dds.rds` y consistencia con `summary_table.tsv`.
- `survey_tcga_rppa.R`: consulta disponibilidad RPPA sin descargar.
- `extract_tcga_rppa_panel.R`: extrae panel de anticuerpos/targets RPPA a `tcga_rppa_panel.tsv` y `tcga_rppa_panel_targets.txt`.
- `download_tcga_rppa.R`: descarga/importa RPPA por cohorte.
- `logs/TCGA-*.log`, `pipeline_stdout.log` y `pipeline_resume_*.log`: trazas de ejecucion y reanudacion del pipeline.
- `CLAUDE.md`, `TCGA_progress_summary.md`, `treated/README.md` y `treated_bulk_rnaseq_candidates.md`: documentacion local del estado del repositorio y de la estrategia para cohortes tratadas.

## Validacion e integridad

La validacion local reporta `pass` para las 33 cohortes. En todos los casos:

- `count_matrix.tsv` es parseable y contiene 59,427 genes.
- `col_data.tsv` es parseable y tiene el mismo numero de filas que columnas de muestra en la matriz de conteos.
- `clinical_data.tsv` es no vacio y parseable.
- `dds.rds` es cargable.
- Los nombres de muestra coinciden entre `count_matrix.tsv` y `col_data.tsv`.
- `sample_type` esta presente.
- La informacion coincide con `summary_table.tsv`.

## Limitaciones importantes

- Este inventario no ejecuta analisis estadistico, normalizacion, DESeq ni comparaciones tumor-normal.
- Los conteos agregados por pacientes se suman por cohorte; un mismo individuo no deberia aparecer en multiples proyectos TCGA, pero el reporte no intenta deduplicar entre cohortes.
- Los caches bajo `gdc_cache/` y `rppa_cache/` son artefactos de descarga. Para analisis reproducible conviene usar los outputs procesados `TCGA-*/` y conservar los caches solo si se necesita reimportar o auditar archivos crudos.
- En RPPA, algunas cohortes tienen paneles mixtos con targets duplicados. Para esas cohortes se debe usar `rppa_expression_matrix.tsv` con `rppa_feature_metadata.tsv`, no asumir una matriz unica por target.
- `treated/` es curacion y manifiestos, no datos tratados materializados. No hay FASTQ ni matrices tratadas descargadas localmente en esa capa.

## Lectura recomendada

Para trabajar con una cohorte, usar primero `TCGA-XXX/count_matrix.tsv`, `TCGA-XXX/col_data.tsv`, `TCGA-XXX/clinical_data.tsv` y, si aplica, `TCGA-XXX/rppa_expression_matrix.tsv` junto con sus metadatos. Para auditoria de origen o redescarga, usar `summary_table.tsv`, `tcga_validation_summary.tsv`, `tcga_rppa_download_summary.tsv`, `logs/` y los caches GDC/RPPA.
