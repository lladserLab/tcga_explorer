# API pública y MCP de TRACE Explorer

TRACE Explorer publica sus flujos científicos mediante una API REST y
un servidor remoto Model Context Protocol (MCP). Ambos usan la misma
validación, cola persistente de cómputo, caché y política de retención.

REST es el contrato público de integración completo. MCP es una superficie
acotada y orientada al análisis sobre el mismo motor científico: permite
descubrir datasets TCGA, externos curados y privados ya cargados, incluidos sus
filtros clínicos específicos; ejecutar los principales flujos de sobrevida y
expresión agrupada; analizar Robustness; y utilizar tanto Pan-cancer de
referencia TCGA como la modalidad jerárquica. Crear o borrar un upload privado y
exportar el Run history del navegador siguen siendo operaciones explícitas de
web/REST.

Los resultados son exploratorios. No están destinados a diagnóstico,
pronóstico, selección de tratamiento ni otras decisiones clínicas.

## Direcciones de producción

| Interfaz | Dirección |
| --- | --- |
| Aplicación web | `https://apps.cienciavida.org/tcga_explorer/` |
| Métodos estáticos de scoring de firmas | `https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/` |
| API REST v1 | `https://apps.cienciavida.org/tcga_explorer/api/v1/` |
| Swagger UI | `https://apps.cienciavida.org/tcga_explorer/api/docs` |
| ReDoc | `https://apps.cienciavida.org/tcga_explorer/api/redoc` |
| OpenAPI 3 | `https://apps.cienciavida.org/tcga_explorer/api/openapi.json` |
| MCP remoto | `https://apps.cienciavida.org/tcga_explorer/mcp` |
| Guía en inglés | `https://apps.cienciavida.org/tcga_explorer/api/guide` |

`/tcga_explorer` es la ruta estable de compatibilidad de TRACE Explorer
y se conserva para marcadores, despliegues Apache y clientes API existentes;
no es otro nombre del producto.

La beta pública no requiere API key. Los límites se aplican a una identidad
anónima derivada de la IP verificada por el proxy o de la sesión MCP.

## Alcance científico y de datos

Las capas de expresión incluyen `coverage`: pacientes únicos vinculados,
columnas de la matriz, tipo de observación y pacientes/eventos por desenlace.
Estos conteos corresponden a la capa elegida antes de seleccionar tejido,
aplicar filtros o excluir registros del modelo. `/endpoints` conserva los
totales del release; para la población de una capa, consultar su `coverage`.

En FU-GBC, la capa fuente contiene 201 perfiles de RNA de 135 pacientes:
135 tumores y 66 tejidos adyacentes pareados. La capa `paired_difference`
contiene 66 contrastes, uno por paciente, calculados como
`log2(TPM_tumor + 1) - log2(TPM_adyacente + 1)`. Un valor positivo indica
mayor expresión en tumor. Cambia la medición y la población; no es otra
normalización ni añade pacientes. El tejido adyacente no constituye un grupo
independiente de controles sanos. REST y MCP usan los mismos conteos por capa.

La API ofrece las mismas capacidades de datos públicos que la interfaz web:

- Resúmenes de cohortes, muestras, pacientes, genes, endpoints y fuentes TCGA.
- Releases curados de RNA-seq bulk independientes, con capas de expresión,
  definiciones de endpoint, licencia y manifiestos inmutables.
- Datasets privados temporales creados desde archivos CSV/TSV desidentificados
  de expresión y metadatos de pacientes. La sobrevida es opcional y los
  datasets nunca se enumeran en el repositorio público.
- Disponibilidad y control de calidad de OS, PFI, DFI y DSS.
- Análisis de gen único y firmas mean, z-score, ponderadas, singscore, ssGSEA
  o AUCell.
- Cox continuo independiente del punto de corte, perfiles con splines cúbicos
  restringidos, diagnóstico de riesgos proporcionales y artefactos reproducibles.
- Kaplan-Meier, Cox agrupado, RMST y sensibilidad al punto de corte como
  análisis secundarios.
- Para DSS, DFI y PFI, codificación explícita de eventos competitivos desde
  TCGA-CDR, funciones de incidencia acumulada, pruebas de Gray y modelos
  Fine-Gray agrupados y continuos junto a los resultados causa-específicos.
- Multiversos prespecificados de endpoint por scoring por punto de corte, con
  corrección por familia, ledger completo y curva de especificaciones.
- Agrupación de dos firmas e interacción Cox continua.
- Paneles acotados de 2--6 firmas, con estandarización en una población común,
  modelos Cox univariables y conjuntos de efectos principales y corrección
  por familia.
- Lotes acotados de comparaciones.
- GSEA prerankeado entre dos grupos definidos por campos clínicos
  estandarizados, dicotomizaciones heredadas de sobrevida o la expresión de un
  gen o firma multigénica.
- Comparación dirigida de expresión para 1--25 genes entre esos mismos grupos
  clínicos, heredados de sobrevida o derivados de expresión, con FDR por genes
  separado para Welch y Mann--Whitney.
- Barridos Cox pan-cáncer continuos, BH-FDR, concordancia y metaanálisis.
- Síntesis pan-cáncer jerárquica opcional de efectos Cox para un gen y OS
  estricto entre universos TCGA y externos curados compatibles.
- Pantallas inmunes pan-cáncer precalculadas.
- Un catálogo de solo lectura con datos tutoriales sintéticos, deterministas y
  bilingües; el progreso educativo permanece local en el navegador.

El alcance público contiene datos abiertos derivados de TCGA/GDC, TCGA-CDR y
releases externos con licencia explícita. No expone rutas internas, manifiestos
de caché, controles de sincronización ni operaciones de base de datos. Una
matriz externa solo se puede descargar si el release permite redistribuirla.

Los uploads privados se direccionan mediante un ID `user-*` no adivinable. Los
archivos originales se eliminan después de validarlos; los datos normalizados
y resultados privados se pueden borrar y vencen a las 24 horas. Un análisis
aceptado que queda en cola o ejecución mantiene vigentes sus inputs privados
durante una ventana adicional de retención; consultar un resultado cacheado ya
completado no extiende ese plazo. El servicio no es un repositorio para
información de salud protegida: solo deben cargarse datos de investigación
desidentificados.

Los artefactos de auditoría a nivel de paciente conservan los barcodes exactos
de participantes y muestras TCGA para trazabilidad científica. Aunque son
identificadores públicos de investigación, no deben usarse para intentar
reidentificar personas ni combinarse con datos restringidos.

### Validación común de solicitudes

La aplicación web, la API REST y el servidor MCP aplican los mismos límites.
Un análisis de gen único requiere exactamente un gen; las firmas mean,
z-score, ponderadas, singscore, ssGSEA y AUCell requieren al menos dos. Al
seleccionar un corte por percentil, también es obligatorio enviar
`custom_percentile` entre 1 y 99.

### Contrato de scoring de firmas

`signature_method` acepta `single`, `mean`, `zscore`, `weighted`, `singscore`,
`ssgsea` o `aucell`. Mean, weighted y z-score operan sobre los componentes
resueltos de la firma. Z-score centra y escala cada gen entre los pacientes
elegibles con expresión completa de esa corrida; sus valores numéricos no son
transportables entre poblaciones puntuadas por separado.

Los tres métodos por rango requieren una capa amplia de expresión congelada
con al menos 1.000 genes únicos utilizables, no más de 75 millones de entradas
gen por muestra y mapeo completo de la firma. Los
genes sin peso y el peso `+1` definen el componente positivo; `-1` define el
negativo. Los clientes REST pueden usar `signature_genes[].direction` con
`up` o `down` y deberían omitir `weight` en esa representación. La dirección
explícita prevalece si se envían ambos campos; se rechazan cero y pesos por
rango no unitarios. `singscore` usa rangos centrados dentro de cada muestra y
es el punto de partida recomendado para RNA bulk. ssGSEA usa
`GSVA::ssgseaParam(alpha=0.25, normalize=FALSE, minSize=2, maxSize=Inf)`; cada
dirección no vacía debe conservar al menos dos genes. AUCell usa una semilla
determinista específica de cada muestra,
`aucMaxRank=ceiling(0.05 * universe_n)` y AUC normalizado, y se etiqueta como
sensibilidad de actividad entre genes altamente expresados. GSVA no se expone
como método.

Los scores por rango se calculan una vez sobre la población molecular canónica
del release, antes de los filtros clínicos y de endpoint, y luego se
seleccionan para el análisis solicitado. Cambiar esos filtros no recalcula el
score de un paciente retenido. Los métodos aritméticos siguen la población
elegible del análisis; z-score se vuelve a calcular sobre sus casos completos.
Los flujos entre estudios estiman los efectos dentro de cada estudio; no
agrupan scores por rango crudos de pacientes como si compartieran una misma
escala numérica.

La página estable [Signature scoring Methods](https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/)
documenta fórmulas, versiones fijadas, universo de genes, manejo de genes
ausentes, dirección y limitaciones sin requerir JavaScript. El archivo
`contract.json` contiguo contiene el mismo contrato en formato legible por
máquinas.

Las edades deben ser finitas y estar entre 0 y 150; la mínima no puede superar
la máxima. `max_time_days`, si se envía, debe ser positivo y no superar
3.652.500 días. Una restricción clínica numérica necesita al menos un límite y
su mínimo no puede superar su máximo. La misma variable clínica no se puede
restringir dos veces. Los lotes públicos aceptan como máximo 25 análisis; los
clientes deben contar genes multiplicados por métodos antes de enviarlos.

Los SHA-256 de auditoría siguen detectando deriva accidental, corrupción y
transferencias incompletas. Además, cada análisis completado recibe un recibo
Ed25519 separado que firma el tamaño y SHA-256 exactos de
`audit_report.json`, su esquema y el hash de reproducibilidad registrado. La
clave debe obtenerse desde el origen HTTPS declarado, no únicamente desde el
export. Esto acredita el origen servidor de ese informe exacto, pero no su
corrección científica ni una fecha de publicación inmutable.

## Inicio rápido con REST

Descubrir la API y sus enlaces canónicos de servicio:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/
```

Revisar disponibilidad y cohortes:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/health

curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/cohorts
```

La respuesta de salud incluye `release.commit` y `release.ref`. Los entornos de
desarrollo informan `development`; un despliegue citable debe exponer el commit
Git completo y el tag exacto definidos mediante `APP_RELEASE_COMMIT` y
`APP_RELEASE_REF`.

## Subir datos propios de expresión y metadatos

Descargar un ejemplo sintético con dos archivos:

```bash
curl -sS -o trace-user-dataset-template.zip \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets/template
```

Ese archivo contiene 18 pacientes sintéticos, tres genes y tres subtipos de seis
pacientes cada uno. Permite probar la carga y la comparación entre dos grupos;
no aporta evidencia biológica ni es apto para GSEA. Para usar los subtipos,
mapear `breast_subtype` como variable categórica con momento basal.
Para listar los paquetes docentes versionados —incluyendo inicio rápido
con 48 muestras, un ejemplo transcriptómico para GSEA y el laboratorio de
validación— use:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/tutorial-assets

curl -sS -o trace-private-quickstart-kirc-log2-v1.zip \
  https://apps.cienciavida.org/tcga_explorer/api/v1/tutorial-assets/private-quickstart-kirc-log2-v1
```

Cada archivo es sintético e incluye README bilingüe, manifiesto versionado, QC
esperado, recetas y checksums SHA-256. La guía escrita completa está en
`docs/TUTORIALS_ES.md`.

Crear un dataset privado temporal mediante multipart. Los metadatos pueden
incluir subtipos u otras variables categóricas o numéricas, y el desenlace de
sobrevida es opcional. No debe definirse manualmente el `Content-Type`; `curl`
agrega el boundary necesario.

```bash
curl -sS \
  -F 'expression_file=@expression.csv' \
  -F 'clinical_file=@clinical.csv' \
  --form-string 'mapping={
    "name": "Cohorte institucional LUAD",
    "cancer_code": "LUAD",
    "expression_orientation": "genes_by_rows",
    "expression_id_column": "gene_symbol",
    "clinical_id_column": "sample_id",
    "has_survival_outcome": true,
    "time_column": "os_months",
    "event_column": "os_status",
    "event_value": "event",
    "censored_value": "censored",
    "time_unit": "months",
    "endpoint": "OS",
    "expression_unit": "log2_tpm",
    "covariates": {
      "age_at_index": "age",
      "stage": "stage",
      "grade": "grade"
    },
    "confirm_deidentified": true
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets
```

La respuesta entrega `id`, `active_release_id`, un `access_token` que se
muestra una sola vez, `expression_layer.value`, las `capabilities` por módulo,
un `endpoint` opcional, avisos QC y `expires_at`. Sin un desenlace utilizable,
el dataset todavía puede usarse en Expression Comparison y, con al menos 100
genes antes de los filtros de cada ejecución, en GSEA. Los pacientes con
desenlace incompleto permanecen en los análisis moleculares y se excluyen solo
de supervivencia. Los tiempos cero o negativos también se excluyen solo de
supervivencia, con un aviso explícito. `qc.endpoint` informa las exclusiones
entre pacientes con expresión; `qc.custom_clinical` resume la cobertura y
disponibilidad de sus agrupaciones. `qc.clinical` conserva los recuentos de la
tabla original, incluidos los registros sin correspondencia.

La expresión debe contener números finitos con punto decimal o faltantes
declarados, como una celda vacía o `NA`. Texto inválido, infinitos y valores
fuera del rango de almacenamiento float32 rechazan la carga con HTTP 422,
una explicación y la fila y columna en `details`. No se convierten
silenciosamente en faltantes. Estas validaciones se aplican a nuevas cargas;
no se reescriben los datasets privados existentes ni su QC registrado.

Los valores del dataset se usan en el request habitual y el token debe enviarse
en cada operación con datos privados:

```bash
curl -H 'X-TRACE-Dataset-Token: TOKEN-DEVUELTO' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets/user-ID-DEVUELTO
```

El navegador conserva el token solo en el almacenamiento de la sesión; al
cerrar la pestaña termina el acceso local. TRACE almacena únicamente su hash
SHA-256. Conocer el ID del dataset no basta para acceder.

```json
{
  "cohort": "TCGA-LUAD",
  "dataset_id": "user-ID-DEVUELTO",
  "dataset_release_id": "user-ID-DEVUELTO-v1",
  "expression_layer_id": "uploaded_expression",
  "gene_symbol": "TP53",
  "endpoint": "OS",
  "cutpoint_method": "median"
}
```

Puede inspeccionarse con `GET /api/v1/user-datasets/{dataset_id}` o borrarse con
`DELETE /api/v1/user-datasets/{dataset_id}`. Debajo de la misma URL existen
recursos para genes, endpoint, capa de expresión y filtros. Los conteos crudos
requieren
al menos 5.000 genes y se convierten a `log2(CPM + 1)`; TPM, FPKM, FPKM-UQ y
CPM no logarítmicos reciben una transformación declarada `log2(x + 1)`. Otras
escalas normalizadas se analizan tal como se entregan. La importación requiere
al menos 10 pacientes pareados. La capacidad de supervivencia requiere además
10 desenlaces completos, 5 eventos y 5 observaciones censuradas. `DELETE`
devuelve HTTP 409 con `USER_DATASET_IN_USE` mientras un trabajo que referencia
el dataset está en cola o ejecución; debe esperarse a que termine y reintentar.

HTTP 429 con `USER_DATASET_LIMIT` indica que la red alcanzó el límite de cargas
activas (tres por defecto). Debe eliminarse un dataset privado al que se tenga
acceso o esperar a que venza una carga. Es un límite diferente al de cómputo;
reintentar un análisis o esperar unos segundos no libera un cupo de carga.

Enviar un análisis:

```bash
curl -i -sS \
  -H 'Content-Type: application/json' \
  -d '{
    "cohort": "TCGA-BRCA",
    "gene_symbol": "TP53",
    "endpoint": "OS",
    "expression_scale": "log2_tpm",
    "cutpoint_method": "median",
    "adjustment_covariates": ["age_at_index"]
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/analyses
```

El endpoint devuelve `202 Accepted`. El cuerpo representa un trabajo
persistente y el encabezado `Location` contiene su URL de estado:

```json
{
  "id": "2f6a...",
  "kind": "analysis",
  "status": "queued",
  "status_url": "https://apps.cienciavida.org/tcga_explorer/api/v1/jobs/2f6a...",
  "result": null,
  "error": null
}
```

Consultar el trabajo hasta obtener `completed`, `failed` o `expired`:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/jobs/JOB_ID
```

Al completar, `result` contiene la respuesta y `result_url` su recurso
permanente durante el período de retención. Solicitudes idénticas activas o
retenidas se deduplican y pueden devolver un resultado en caché. La identidad
del trabajo incluye la solicitud, la versión del pipeline y la versión de los
datos; un contexto científico nuevo no reutiliza un artefacto completado bajo
uno anterior.

Enviar un panel de efectos principales de múltiples firmas:

```bash
curl -i -sS \
  -H 'Content-Type: application/json' \
  -d '{
    "cohort": "TCGA-SKCM",
    "panel_name": "Programas inmunes",
    "endpoint": "OS",
    "expression_scale": "log2_tpm",
    "signatures": [
      {
        "name": "Efectora",
        "gene_symbol": "IFNG, CXCL9, GZMB",
        "signature_method": "zscore",
        "signature_genes": [
          {"gene_symbol": "IFNG", "weight": 1},
          {"gene_symbol": "CXCL9", "weight": 1},
          {"gene_symbol": "GZMB", "weight": 1}
        ]
      },
      {
        "name": "Checkpoint",
        "gene_symbol": "PDCD1, LAG3, HAVCR2",
        "signature_method": "zscore",
        "signature_genes": [
          {"gene_symbol": "PDCD1", "weight": 1},
          {"gene_symbol": "LAG3", "weight": 1},
          {"gene_symbol": "HAVCR2", "weight": 1}
        ]
      }
    ],
    "adjustment_covariates": ["age_at_index", "stage"]
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/analyses/signature-panel
```

El panel exige 2--6 nombres y definiciones únicas. Intersecta pacientes con
endpoint y todos los scores completos, y estandariza cada score sobre esa
población común. Ajusta sólo efectos principales continuos: un Cox univariable
por firma, un modelo conjunto no ajustado y un conjunto con el ajuste clínico
exacto cuando se solicita y es evaluable. No busca puntos de corte, no crea
grupos Kaplan--Meier ni infiere interacciones.

## Catálogo de endpoints

### Servicio y dataset

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/health` | Versiones, datos, caché y cola |
| `GET` | `/dataset/summary` | Resumen, filtrable por `cohort` |
| `GET` | `/dataset/summary/download/csv` | Resumen CSV |
| `GET` | `/data-sources` | Procedencia sanitizada |
| `GET` | `/endpoints` | Disponibilidad global de endpoints |
| `GET` | `/expression-scales` | Escalas RNA soportadas |
| `GET` | `/attestation/keys` | Claves públicas Ed25519 activas y conservadas |
| `GET` | `/attestation/keys/{key_id}` | Documento de una clave pública exacta |

### Descubrimiento por cohorte

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/cohorts` | Listar cohortes |
| `GET` | `/cohorts/{cohort_id}/endpoints` | Cobertura y QC de endpoints |
| `GET` | `/cohorts/{cohort_id}/filters` | Filtros clínicos disponibles |
| `GET` | `/cohorts/{cohort_id}/genes` | Buscar genes de la referencia TCGA |
| `GET` | `/cohorts/{cohort_id}/genes/resolve` | Resolver símbolo o alias de TCGA |

Para cánceres exclusivamente externos, como `FU-GBC`, selecciona un `dataset_id`
y usa `/datasets/{dataset_id}/genes` o `/datasets/{dataset_id}/genes/resolve`.
Las rutas de genes TCGA devuelven `422 DATASET_REQUIRED` en estos casos, sin
intentar cargar una matriz TCGA. En MCP corresponden las herramientas
`trace_search_dataset_genes` y `trace_resolve_dataset_gene`.
La misma regla se aplica a `/cohorts/{cohort_id}/endpoints` y `/filters`:
devuelven `422 DATASET_REQUIRED`, no un falso recuento de cero pacientes.
Usa `/datasets/{dataset_id}/endpoints` y `/filters`, o las herramientas MCP
`trace_get_dataset_endpoints` y `trace_get_dataset_filter_options`.

Swagger UI y ReDoc cargan recursos locales fijados por versión, sin CDN ni
validador externo. Los enlaces a la guía y al OpenAPI siguen disponibles
si JavaScript está deshabilitado o falla la carga del esquema.

Las respuestas de filtros incluyen `clinical_grouping_variables`, un catálogo
versionado compartido por GSEA y comparación de expresión. Cada variable
informa `id` estable, etiqueta, tipo, categoría, campo fuente, cobertura por
paciente, faltantes, disponibilidad y
`levels[{value,label,count,analysis_eligible,unavailable_reason}]` para datos
categóricos. Cada entrada incluye además `provenance`, con `origin`,
`reported_by`, `method_summary`, una `reference` bibliográfica opcional,
`expression_derived`, `recomputed_by_trace` y una declaración de
`comparability` entre estudios. TRACE distingue campos clínicos armonizados,
anotaciones informadas por la fuente, llamadas moleculares informadas por la
fuente y variables declaradas por el usuario; nunca transforma silenciosamente
una clase en otra. Los niveles con menos de cinco pacientes siguen visibles para
auditoría, pero no pueden seleccionarse como grupo individual; las variables
continuas entregan un resumen numérico. El servidor valida el ID y los niveles contra
la cohorte o release activo. En TCGA el catálogo se cura explícitamente desde
metadatos estandarizados, filas GDC marcadas como diagnóstico primario, campos
TCGA-CDR y anotaciones seleccionadas de los marker papers; no se aceptan
identificadores, tiempos de sobrevida ni columnas técnicas no declaradas. En
releases externos se combinan metadatos namespaced de paciente y muestra, se
decodifican objetos serializados con tamaño acotado, se canonizan categorías
equivalentes y se omiten duplicados de campos estandarizados. Las variables de
baja cobertura o postresección conservan advertencias de interpretación.

### Repositorio curado de RNA-seq bulk externo

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/cancer-types` | Cobertura de enfermedades TCGA y entidades registradas sólo como externas |
| `GET` | `/datasets` | Releases listos para cómputo, con filtro opcional por `analysis_type` |
| `GET` | `/dataset-candidates` | Candidatos revisados, decisiones y bloqueos; sólo descubrimiento |
| `GET` | `/datasets/{dataset_id}` | Fuente, licencia, QC, endpoints y capa de expresión |
| `GET` | `/datasets/{dataset_id}/endpoints` | Definiciones y QC de endpoints del release |
| `GET` | `/datasets/{dataset_id}/expression-layers` | Unidad, transformación y advertencias de escala |
| `GET` | `/datasets/{dataset_id}/filters` | Filtros clínicos curados disponibles |
| `GET` | `/datasets/{dataset_id}/genes` | Buscar genes en una capa fijada |
| `GET` | `/datasets/{dataset_id}/genes/resolve` | Resolver un gen en una capa fijada |
| `GET` | `/datasets/{dataset_id}/download/{kind}` | Descargar manifiesto, QC, licencia o matriz/metadata/genes autorizados |

Cada elemento de `/datasets` incluye `capabilities`, `available_modules` y un
arreglo `endpoints` con código, nombre, número de pacientes, eventos, origen
temporal y definición del evento. Por ejemplo,
`/datasets?analysis_type=gsea` devuelve sólo releases compatibles. La ruta
específica del endpoint conserva el detalle autoritativo.

`/dataset-candidates` permanece separado deliberadamente. Permite filtrar por
`disease_id`, `status`, `analysis_type` y `query`, pero un candidato no puede
enviarse a cómputo hasta que pase QC y aparezca como release versionado en
`/datasets`.

Para analizar un release externo, se usa el identificador de cohorte devuelto
por el catálogo y se fijan dataset, release y capa. Las enfermedades cubiertas
por TCGA conservan ese identificador; las enfermedades sólo externas usan su
identificador `EXT-*` registrado (por ejemplo `EXT-CLL`):

```json
{
  "cohort": "TCGA-BLCA",
  "dataset_id": "cbioportal-blca-iatlas-imvigor210-2017",
  "dataset_release_id": "cbioportal-blca-iatlas-imvigor210-2017-1da5c747e4fd",
  "expression_layer_id": "provided_tpm_profile",
  "gene_symbol": "MKI67",
  "endpoint": "OS",
  "cutpoint_method": "median",
  "adjustment_covariates": []
}
```

Cuando `dataset_id` está presente, el análisis no utiliza pacientes ni
expresión de TCGA. Cada release externo admite sólo los flujos declarados en
su bloque de capacidades: una cohorte molecular puede admitir comparación de
expresión y GSEA sin ser elegible para supervivencia. Las solicitudes no
compatibles se rechazan antes de entrar a la cola, con una razón y las opciones
disponibles. Dentro de Pan-cancer, el
modo **TCGA reference** continúa limitado a TCGA; el modo separado y opcional
**TCGA + external hierarchical** puede incluir releases externos elegibles
como universos de estudio distintos. Nunca agrega sus columnas de expresión a
una matriz TCGA.

### Ejemplos reproducibles del paper

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/examples/paper` | Benchmark, diagnósticos y catálogo de figuras del manuscrito |
| `GET` | `/examples/paper/figures/{analysis_id}/{kind}` | Figura fijada del benchmark (`continuous`, `km` o `cox`) |

Las figuras de ejemplo están fijadas al benchmark versionado del manuscrito y
no se eliminan con la retención normal de 90 días. El catálogo conserva
resultados positivos, no soportados, sensibles al endpoint y diagnósticos,
incluidos los casos pan-cáncer BIRC5 y CA9 con comparación primaria frente a
sensibilidad ordinal.

### Análisis y trabajos

| Método | Ruta | Función |
| --- | --- | --- |
| `POST` | `/analyses` | Enviar análisis de un gen o firma |
| `POST` | `/analyses/combined` | Enviar análisis de dos firmas |
| `POST` | `/analyses/signature-panel` | Enviar panel de 2--6 firmas con efectos principales |
| `POST` | `/analyses/batch` | Enviar hasta 25 análisis |
| `POST` | `/analyses/multiverse` | Enviar un análisis de Robustness (familia declarada de especificaciones) |
| `GET` | `/gsea/collections` | Listar colecciones congeladas y métricas de ranking |
| `POST` | `/analyses/gsea` | Enviar un análisis de vías entre dos grupos con CAMERA y efectos prerankeados descriptivos |
| `POST` | `/analyses/expression-comparisons` | Enviar una comparación dirigida de expresión entre dos grupos |
| `POST` | `/analyses/sessions/export` | Exportar trabajos seleccionados como un registro exploratorio |
| `GET` | `/jobs/{job_id}` | Consultar cualquier trabajo |
| `GET` | `/analyses/{analysis_id}` | Recuperar un análisis |
| `GET` | `/analyses/batches/{batch_id}` | Recuperar un lote |
| `GET` | `/analyses/multiverses/{session_id}` | Recuperar un análisis de Robustness completado |
| `GET` | `/analyses/multiverses/{session_id}/download/{kind}` | Descargar un artefacto de Robustness |
| `GET` | `/analyses/gsea/{gsea_id}` | Recuperar un GSEA completado |
| `GET` | `/analyses/gsea/{gsea_id}/download/{kind}` | Descargar un artefacto GSEA |
| `GET` | `/analyses/expression-comparisons/{comparison_id}` | Recuperar una comparación de expresión completada |
| `GET` | `/analyses/expression-comparisons/{comparison_id}/download/{kind}` | Descargar un artefacto de comparación de expresión |
| `GET` | `/analyses/sessions/{report_id}` | Recuperar un registro exploratorio |
| `GET` | `/analyses/sessions/{report_id}/download/{kind}` | Descargar un artefacto de sesión |
| `GET` | `/analyses/{analysis_id}/download/{kind}` | Descargar artefacto |

Los lotes de Compare completados incluyen `grouped_family`, versión
`compare-grouped-family-v1`, tanto por REST como por MCP: conteos `requested`,
`completed`, `failed`, `evaluable`, `unavailable` y lista `tests` indexada con
`test`, `p_value`, `bh_q_value` y `bonferroni_p_value`. Maxstat utiliza primero
su p corregido por selección (Lau94), nunca el log-rank descriptivo como reemplazo.
Los cortes fijos utilizan log-rank. BH y Bonferroni abarcan los tests agrupados
válidos del lote enviado. Los fallidos y los p corregidos ausentes se cuentan y
permanecen visibles, con ajustes nulos, pero no integran el denominador.
Esta familia evaluable no corrige la selección de análisis exitosos ni la
selección entre ejecuciones. Cox continuo, Cox agrupado y RMST son evidencia
separada. El CSV resumen de Compare registra la familia; las descargas por
análisis conservan su alcance individual. Los lotes anteriores pueden carecer
de `grouped_family`; la nueva versión participa en la clave de caché de lotes.

Tipos de descarga de análisis: `zip`, `continuous_png`, `continuous_svg`,
`continuous_csv`, `png`, `svg`, `cox_png`, `cox_svg`,
`cox_univariable_png`, `cox_univariable_svg`, `cox_multivariable_png`,
`cox_multivariable_svg`,
`signature_panel_joint_png`, `signature_panel_joint_svg`,
`signature_panel_adjusted_png`, `signature_panel_adjusted_svg`,
`model_results_csv`, `score_correlations_csv`,
`cumulative_incidence_png`, `cumulative_incidence_svg`, `csv`, `json`,
`audit_json`, `audit_html`, `attestation`, `txt` y `methodology`.

El pipeline v6.15 agregó
`plot_style.cox_forest.model_layout: "combined" | "separate"`. `combined`
continúa siendo el valor por defecto. `separate` crea un forest univariado
adicional y otro con todos los modelos multivariables ajustados que hayan
podido estimarse; cada archivo se omite si su familia no es evaluable. Los
campos opcionales `univariable_plot_title` y `multivariable_plot_title`
personalizan esos títulos. `cox_png` y `cox_svg` se conservan para
compatibilidad retroactiva.

El pipeline v6.17 agrega tipografía y bordes compartidos para los ejes:
`axis_text_bold`, `axis_text_italic`, `axis_title_bold`,
`axis_title_italic` y `plot_frame: "open" | "axes" | "box"`. Los valores por
defecto siguen siendo texto normal y un panel abierto. Estos campos afectan
las figuras Kaplan-Meier, Cox continuo, Cox agrupado, riesgos competitivos y
paneles de firmas sin cambiar ningún modelo ajustado. La especificación
completa queda registrada en la solicitud, identidad de caché, auditoría y
metodología.

El pipeline v6.18 exige separar los brazos aleatorizados en todo análisis PFS
de IMmotion150. El catálogo de filtros expone `study_arm` con las tres
asignaciones originales: `Atezolizumab`, `Atezolizumab + Bevacizumab` y
`Sunitinib`. Cada solicitud debe incluir uno, y solo uno, de estos niveles en
`filters.custom_filters`; las solicitudes PFS combinadas se rechazan en todos
los puntos de entrada de sobrevida, incluidos batch, Robustness y MCP.

El pipeline v6.19 conserva esa regla y aplica a los forest plots univariados y
multivariados renderizados por separado una misma escala log-HR, ancho físico y
espaciado entre filas. Los contratos v4.10 de firmas combinadas, v1.3 del panel
de firmas y v2.5 de Robustness incorporan la misma comparabilidad visual.

El pipeline de panel v1.0 aplica BH y Bonferroni por separado a los términos de
firma de las familias univariable, conjunta y ajustada. Los términos clínicos
no integran esas familias. Las correlaciones Pearson/Spearman y la
superposición/Jaccard de genes son contexto descriptivo y no activan un umbral
de advertencia. Para DSS, DFI y PFI se informan familias Fine--Gray
correspondientes cuando la codificación de eventos es evaluable.

Desde la versión v6.0, cada análisis de un gen o de una firma calcula primero
un Cox por +1 desviación estándar intranálisis del score, usando toda la
población elegible con expresión completa. Esa misma población alimenta un
perfil spline cúbico restringido de tres grados de libertad, con nodos en los
percentiles 5, 35, 65 y 95. La prueba de razón de verosimilitudes entre spline
y tendencia lineal se informa como diagnóstico de no linealidad, no como regla
binaria. `metrics.continuous_analysis` contiene los modelos lineales, el perfil
spline, la escala del predictor, el tamaño poblacional y los eventos. Estos
resultados no cambian cuando solo cambia el punto de corte solicitado.

El pipeline v6.2 acepta una lista opcional `adjustment_covariates` para un
modelo ajustado exacto, estimado por casos completos. Los campos importados
admitidos son `age_at_index`, `stage`, `grade`, `gender` y `race`. La edad se
modela de forma continua por cada 10 años; el estadio patológico mayor
(`0`, `I`, `II`, `III`, `IV`) y el grado histológico (`G1`–`G5`) como
tendencias ordinales; género y raza GDC como contrastes categóricos. Los
valores faltantes, desconocidos o no estándar se excluyen de ese modelo.

El pipeline v6.7 también acepta un dataset versionado
`external_covariates` y una selección explícita
`external_adjustment_covariates`. El enlace se realiza por barcode exacto del
participante TCGA después de construir la población con expresión completa.
Se admiten hasta 10 variables y 2.000 participantes únicos. Solo se permiten
identificadores públicos TCGA; no deben enviarse nombres, identificadores
locales ni datos clínicos protegidos.

```json
{
  "external_covariates": {
    "schema_version": "tcga-trace-external-covariates-v1",
    "source_label": "Anotaciones LGG curadas",
    "definitions": [
      {
        "name": "idh_status",
        "label": "Estado IDH",
        "value_type": "categorical",
        "levels": ["Wild type", "Mutant"],
        "reference_level": "Wild type"
      },
      {
        "name": "tumor_purity",
        "label": "Pureza tumoral",
        "value_type": "continuous",
        "unit": "proportion",
        "effect_unit": 0.1
      },
      {
        "name": "molecular_risk",
        "label": "Riesgo molecular",
        "value_type": "ordinal",
        "levels": ["Low", "Intermediate", "High"]
      }
    ],
    "rows": [
      {
        "patient_id": "TCGA-AB-0001",
        "values": {
          "idh_status": "Mutant",
          "tumor_purity": 0.72,
          "molecular_risk": "High"
        }
      }
    ]
  },
  "external_adjustment_covariates": [
    "idh_status",
    "tumor_purity",
    "molecular_risk"
  ]
}
```

Las variables continuas usan la unidad de efecto declarada; las categóricas
usan contrastes contra `reference_level`; las ordinales usan una tendencia de
un nivel según el orden declarado en `levels`. Los datos faltantes se manejan
por casos completos en cada modelo. El dataset normalizado participa en la
identidad de la solicitud y el hash reproducible. La auditoría conserva su
SHA-256, QC de enlace y missingness, definiciones, selección y valores por
paciente.

El modelo exacto se añade a las familias continua, agrupada y de interacción
entre dos firmas. Los modelos fijos por estadio, grado y estadio más grado se
conservan como sensibilidades auxiliares. Si el ajuste solicitado no es
evaluable, la respuesta informa `not_evaluable` y no lo reemplaza por otro
modelo auxiliar. Cada Cox registra pacientes y eventos por casos completos,
parámetros ajustados, eventos por parámetro y metadatos
`covariate_encoding`.

Desde la versión v6.1, cada Cox continuo, agrupado y de interacción entre dos
firmas también contiene:

- `information_diagnostics`: número de parámetros ajustados, eventos
  observados, eventos por parámetro, estado `adequate`/`caution`/`severe`,
  umbrales, inestabilidad del ajuste estándar, estimación extrema y motivos del
  disparador.
- `penalized_sensitivity`: `not_triggered`, `completed` o `failed`. Un resultado
  completado usa verosimilitud parcial penalizada de Firth con `coxphf`
  (penalización 0,5), intervalos y pruebas de perfil penalizado, y registra
  empates Breslow, iteraciones, versión del paquete, efecto y disparador.

Se marca cautela bajo 10 eventos por parámetro ajustado y cautela severa bajo
5. Son diagnósticos de interpretación, no reglas de exclusión. El Cox estándar
con `survival::coxph` conserva empates Efron y sigue siendo el ajuste principal;
Firth se informa como sensibilidad adyacente.

Kaplan-Meier, Cox agrupado y RMST son vistas secundarias de sensibilidad al
punto de corte. Maxstat está optimizado contra el desenlace; sus efectos
agrupados y RMST siguen siendo resúmenes post-selección. Las pruebas
`cox.zph` del marcador y del modelo global se informan por separado y modifican
la interpretación, sin descartar una asociación.
Cuando el `cox.zph` específico del marcador tiene p < 0,05, los modelos Cox
agrupados, continuos, de interacción y pan-cáncer también entregan
`time_varying_effect`. El diagnóstico usa un corte primario fijo en 730,5 días
y sensibilidades fijas a 1 y 5 años:

- `status`: `completed`, `skipped`, `failed`, `not_triggered` o
  `not_evaluable`;
- `periods.early` y `periods.late`: soporte, HR, IC 95% y p de cada período;
- `change`: razón entre el HR tardío y temprano, IC 95% y p;
- `support`: eventos a cada lado y pacientes que entran al período tardío; y
- `sensitivity_analyses`: el mismo contrato para los cortes a 1 y 5 años; y
- disparador, regla del corte fijo, soporte mínimo, manejo de empates y
  especificación de varianza robusta.

El corte nunca se elige desde la expresión, tiempos de evento, puntos de corte
ni efectos estimados. Se requieren al menos 5 eventos por período y 10
pacientes que entren al período tardío. La razón es el contraste Wald de la
interacción marcador-período y cada ajuste en dos períodos es una aproximación
gruesa a un efecto que podría variar suavemente en el tiempo. Es un diagnóstico
para interpretar PH, no una prueba primaria adicional ni una regla de
exclusión. Los CSV continuos y agrupados del multiverso conservan los mismos
campos.

### Estimandos con riesgos competitivos

El pipeline de análisis v6.10 usa las columnas de estado y tiempo
`ExtraEndpoints` de TCGA-CDR para DSS, DFI y PFI. La codificación estructurada
es:

- `0`: censura;
- `1`: evento de interés; y
- `2`: muerte competitiva específica del endpoint.

En DSS, el evento de interés es la muerte por el cáncer índice y el código 2
corresponde a muerte por otra causa. En DFI, el código 1 representa recurrencia
después de un intervalo libre de enfermedad y el código 2, muerte antes de una
recurrencia documentada. En PFI, el código 1 representa progresión o muerte con
tumor y el código 2, muerte sin una progresión previa.

Kaplan-Meier y Cox siguen censurando el código 2 en su tiempo registrado. Por
lo tanto, describen supervivencia libre del evento y el hazard causa-específico
bajo el supuesto de censura correspondiente. `metrics.competing_risks`
conserva el código 2 como evento competitivo e informa otro estimando:

- `coding`: columnas fuente, etiquetas y contratos de ambos estimandos;
- `cumulative_incidence`: curvas no paramétricas por grupo, conteos de estados,
  prueba K-muestras de Gray y estimaciones a 1, 3 y 5 años;
- cada horizonte incluye IC 95% puntual con varianza de Aalen, pacientes en
  riesgo y cautela cuando quedan menos de 5;
- `grouped_fine_gray_models`: SHR para los grupos de expresión; y
- `continuous_fine_gray_models`: SHR por +1 DE de expresión intranálisis.

Las familias Fine-Gray incluyen modelos univariables, el ajuste exacto
solicitado por el usuario y los auxiliares disponibles por estadio/grado. Cada
modelo informa sus propios casos completos, eventos de interés, eventos
competitivos, parámetros, eventos por parámetro, codificación, contraste, SHR,
IC 95% y p. Los modelos sin soporte permanecen visibles con su razón. OS
devuelve `applicable: false`; si un endpoint competitivo no contiene ningún
evento código 2, conserva el contrato pero omite la estimación.

El HR causa-específico y el SHR Fine-Gray responden preguntas distintas y nunca
se presentan como intercambiables. El PNG/SVG de CIF, el resultado
estructurado, metodología, auditoría JSON/HTML, CSV de pacientes, helper R
exacto y cápsula reproducible conservan la misma codificación y resultado.

Las respuestas de análisis completados también incluyen dos campos para apoyar
la interpretación:

- `notices`: mensajes estructurados con `category` (`cohort`, `method`,
  `model` o `availability`), `severity` (`info`, `caution`,
  `not_evaluable` o `error`), alcance decisional `scope` (`primary`,
  `requested_adjustment`, `auxiliary` o `context`) y `priority` (`high`,
  `medium` o `low`).
- `diagnostics`: modelo primario orientado a la decisión y, cuando se declara
  en la solicitud, el modelo clínico ajustado exacto, con identificador, etiqueta,
  familia y estado. El estado primario usa `clean`, `caution` o
  `not_evaluable`; el estado ajustado también usa `not_requested` cuando no se
  declaró un ajuste. Los conteos de mensajes se informan por separado.

Las fallas y cautelas del resultado primario nunca se ocultan. Sin un ajuste
clínico declarado, el modelo no ajustado permanece como primario; stage, grade
y stage+grade son sensibilidades auxiliares. Cuando se solicita un ajuste, sus
covariables exactas se fijan antes del análisis y ese modelo pasa a ser el
resultado orientado a la decisión, manteniendo visible el no ajustado. Un
ajuste solicitado que no sea evaluable permanece visible sin invalidar un
resultado no ajustado disponible. Los diagnósticos auxiliares y la procedencia
de cohorte/método quedan disponibles con menor prioridad y no contaminan el
estado primario. El arreglo histórico `warnings` se conserva por
compatibilidad; clientes nuevos deberían preferir `notices` y `diagnostics`.

### Robustness a través de decisiones analíticas

La ruta de API se mantiene como `POST /analyses/multiverse` por compatibilidad.
Impulsa la interfaz **Robustness** mediante análisis multiverse y curva de
especificación preespecificados, y recibe una cohorte, un gen o firma multigénica, uno
o más endpoints que pasen el QC, métodos de scoring compatibles y uno o más
métodos de corte. El producto cartesiano completo se congela antes de ejecutar
y admite hasta 72 especificaciones.

La respuesta separa dos familias de multiplicidad:

- `continuous_references`: un Cox independiente del corte por combinación
  única de endpoint y scoring. Repetir puntos de corte no repite esta prueba.
- `specifications`: todas las sensibilidades endpoint por scoring por corte.
  Maxstat usa su p corregido Lau94 para la multiplicidad agrupada; su HR
  agrupado y RMST permanecen rotulados como post-selección.

BH y Bonferroni se calculan por separado dentro de cada familia. Los
diagnósticos PH modifican la interpretación y no generan un veredicto
retenido/no retenido. El ledger conserva cada celda planificada, incluidos
fallos de QC y modelos no evaluables, junto con hashes de solicitud, IDs de
análisis hijo y hashes de auditoría. Su alcance es la familia declarada, no
otras corridas ad hoc de la sesión del navegador.

Tipos de descarga de Robustness: `svg`, `csv`, `continuous_csv`, `ledger`, `json`,
`audit_json`, `audit_html`, `attestation`, `methodology` y `zip`.

### Análisis de pathways entre dos grupos con ajuste de correlación

`POST /analyses/gsea` evalúa la colección fijada por el servidor con limma
CAMERA y además ordena los genes mediante un contraste explícito grupo B menos
grupo A para obtener ES, NES y leading edge descriptivos. Un NES positivo
favorece al grupo B y uno negativo al grupo A. Las fuentes de agrupación son:

- `clinical`: niveles disjuntos de una variable declarada en el catálogo
  `clinical_grouping_variables` del dataset, o umbral mediano/fijo para
  cualquier variable numérica declarada. Incluye, cuando están disponibles,
  estadio, edad, pack-years, PAM50 en BRCA, IDH/1p19q en gliomas y anotaciones
  histológicas o MSI;
- `survival`: las asignaciones exactas de muestra conservadas por un análisis
  de sobrevida completado, identificado mediante `survival_analysis_id`;
- `expression`: un gen o una firma mean, z-score, ponderada, singscore, ssGSEA
  o AUCell, dividida por mediana, cuartil superior, cuartiles extremos o
  percentil declarado.

Los valores p primarios usan limma CAMERA 3.62.2 con diseño B menos A,
moderación empírico-bayesiana con tendencia media--varianza y correlación
residual entre genes estimada por separado para cada conjunto
(`inter.gene.cor=NA`, `allow.neg.cor=FALSE`). Benjamini--Hochberg ajusta los
valores p competitivos bilaterales en toda la colección elegible. La respuesta
registra dirección CAMERA, correlación estimada, dirección NES y su concordancia.
Los resúmenes de vías que cumplen el FDR de CAMERA se asignan a cada grupo según
la dirección de CAMERA; la dirección NES permanece como descriptor separado.

El ranking descriptivo usa t de Welch no moderado o signal-to-noise. Las
permutaciones de conjuntos se usan únicamente para normalizar ES a NES; sus
valores p no se entregan ni sostienen inferencia. Solo genes variables con datos
completos entran en ambas capas. Los grupos derivados de expresión, incluidos
PAM50 y los heredados de un análisis de sobrevida basado en expresión, se
rotulan `conditional_exploratory`: sus p/FDR describen el contraste observado,
pero no son confirmación independiente. Los grupos maxstat heredados reciben
además una advertencia de circularidad informada por el desenlace.

Los resultados GSEA completados con schema v1 siguen disponibles para lectura
y descarga reproducible. Sus valores p y FDR originales por permutación de
gene sets se identifican como método histórico y nunca se presentan como
evidencia CAMERA. Toda corrida nueva usa schema v2; TRACE no reescribe ni
reinterpreta los artefactos v1.

El CSV de grupos conserva a cada paciente considerado tras elegibilidad y
matching con la matriz. Registra valor clínico resuelto, ID y campo fuente; los
pacientes fuera del contraste binario permanecen auditables mediante
`missing_clinical_value` o `unselected_clinical_level`.

Las solicitudes de Survival, Compare, Robustness, comparación de expresión y
GSEA pueden incorporar hasta diez restricciones declaradas por el catálogo en
`filters.custom_filters`. Cada `variable_id` y sus niveles observados deben
obtenerse desde `clinical_grouping_variables` para el dataset seleccionado.
Los niveles elegidos dentro de una variable usan OR; variables diferentes usan
AND. Las variables numéricas aceptan mínimo, máximo o ambos. Estas
restricciones modifican la población elegible y quedan auditadas, pero nunca se
convierten automáticamente en covariables Cox.

Por ejemplo, para comparar AJCC N dentro de PAM50 Luminal A en TCGA-BRCA:

```json
{
  "filters": {
    "sample_population": "primary_solid",
    "custom_filters": [
      {
        "variable_id": "paper_BRCA_Subtype_PAM50",
        "categorical_levels": ["LumA"]
      }
    ]
  },
  "grouping": {
    "source": "clinical",
    "clinical_variable": "ajcc_pathologic_n",
    "group_a_values": ["N0"],
    "group_b_values": ["N1", "N1a", "N1b", "N1c", "N2", "N3"]
  }
}
```

Los niveles N exactos deben elegirse desde el catálogo activo. Una misma
variable no puede definir los grupos y además aparecer en `custom_filters`.
PAM50 es una llamada de TCGA-BRCA informada por los autores y derivada de
expresión; TRACE no vuelve a ejecutar el clasificador. Conserva advertencias de
circularidad y comparabilidad metodológica entre estudios. TRACE no
rotula Basal-like PAM50 como TNBC: TNBC requiere ER negativo, PR negativo y
HER2 negativo observados.

Cada corrida completada conserva el landscape NES y agrega un DotPlot
reproducible para hasta 30 pathways con menor FDR de CAMERA. La posición y el
color divergente codifican NES descriptivo con una escala azul
oscuro-blanco-rojo centrada en cero; el área del punto es proporcional a
`min(-log10(FDR CAMERA), 10)`. Las leyendas
están sobre el panel limpio, los pathways se etiquetan a la derecha y una línea
vertical discontinua marca NES 0. El cap y la dirección de ambos grupos quedan
impresos en el SVG accesible. La auditoría registra su checksum y el ZIP firmado
lo incluye.

El catálogo incluido y verificado por checksum contiene un GMT ImmPort
congelado con 153 listas inmunes y tres colecciones humanas separadas de Gene
Ontology: Biological Process (8.195 conjuntos), Molecular Function (2.202) y
Cellular Component (1.287). GO usa el release oficial 2026-06-19
(DOI:10.5281/zenodo.20943148, CC BY 4.0); las anotaciones directas se propagan
exactamente por `is_a` y `part_of`, y se excluyen anotaciones con `NOT` y
términos obsoletos. `GET /gsea/collections` expone release, atribución y
checksums de fuentes y salidas. Los trabajos no descargan conjuntos durante la
ejecución. La procedencia completa de generación y el aviso de atribución se
documentan en `backend/gene_sets/README.md`. Tipos de descarga GSEA: `csv`,
`ranking_csv`, `groups_csv`, `leading_edges_csv`, `svg` (landscape NES),
`dotplot_svg`, `json`, `input`, `gene_set_manifest`, `audit_json`,
`methodology`, `camera_r_script` y `zip`. Las corridas nuevas también incluyen `attestation`, el
recibo Ed25519 separado del informe de auditoría.

### Comparación de expresión entre grupos

`POST /analyses/expression-comparisons` compara entre 1 y 25 genes solicitados
en una agrupación binaria. Acepta las mismas definiciones `clinical`,
`survival` y `expression` documentadas para GSEA: variables clínicas
estandarizadas, asignaciones exactas de un resultado de sobrevida no vencido o
el corte de un score de uno o varios genes. La escala de expresión normalizada
y los filtros de cohorte quedan declarados en el request.

Para cada gen target utilizable informa tamaños, medias, medianas y dispersión
por grupo, además de la diferencia de expresión grupo B menos grupo A. Calcula
una prueba t de Welch con varianzas desiguales y una sensibilidad rank-sum de
Mann--Whitney cuando corresponde inferencia. Un target que forma parte de la
firma usada para construir el grupo por expresión queda `descriptive_only`,
con p/FDR nulos y `significant_at_fdr: false`. Benjamini--Hochberg se aplica
por separado a los demás genes solicitados e inferencialmente evaluables de
las familias Welch y Mann--Whitney; no representa una corrección sobre toda la
matriz. Los
targets sin solape bajo agrupación por expresión mantienen inferencia
exploratoria, y los grupos maxstat heredados conservan la advertencia de
circularidad informada por el desenlace.
Si la agrupación clínica fue derivada de expresión transcriptómica, como
PAM50, todos los targets quedan `descriptive_only`, con p/FDR nulos y fuera de
ambas familias BH.

Ejemplo:

```json
{
  "cohort": "TCGA-LIHC",
  "expression_scale": "log2_tpm",
  "genes": ["CDC20", "BIRC5", "MKI67"],
  "grouping": {
    "source": "clinical",
    "clinical_variable": "stage",
    "group_a_values": ["Stage I", "Stage II"],
    "group_b_values": ["Stage III", "Stage IV"],
    "group_a_label": "Temprano",
    "group_b_label": "Avanzado"
  },
  "fdr_threshold": 0.05
}
```

Tipos de descarga: `values_csv`, `groups_csv`, `statistics_csv`,
`violin_svg`, `boxplot_svg`, `heatmap_svg`, `json`, `input`, `methodology`,
`audit_json`, `attestation` y `zip`. El ZIP completo contiene `input.json`,
`expression_values.csv`, `sample_groups.csv`, `gene_statistics.csv`, los tres
SVG, `methodology.txt`, `result.json`, `audit_report.json` y
`attestation_receipt.json`. La auditoría enlaza por SHA-256 el request, las
asignaciones, los valores de expresión, las estadísticas y el resultado central
acotado, además de registrar todos los artefactos renderizados.
El contrato de caché y auditoría se versiona como
`grouped-expression-comparison-welch-wilcoxon-bh-contract-v1.4`.

### Historial exploratorio de sesión

`POST /analyses/sessions/export` acepta hasta 200 eventos seleccionados que
referencian valores `job_id` terminales, además de etiquetas y tiempos anotados
por el navegador. El servidor resuelve las solicitudes y resultados
autoritativos desde sus registros de cómputo. El informe no incorpora
registros por paciente ni valores de las filas de covariables externas.

BH y Bonferroni se aplican por separado a hipótesis únicas Cox continuas,
sensibilidades agrupadas por corte e interacciones de dos firmas. Las hipótesis
idénticas se cuentan una vez, aunque cada evento repetido permanece en el
ledger. Robustness, pan-cáncer, paneles de firmas, GSEA y comparaciones de
expresión agrupadas conservan su corrección interna y se listan solo como
referencias. El alcance es post hoc y depende de la selección exportada: no
prueba que no existan otras corridas ni genera un veredicto retenido/no
retenido.

Tipos de descarga: `json`, `runs_csv`, `hypotheses_csv`, `ledger`,
`audit_json`, `audit_html`, `attestation`, `methodology` y `zip`.

### Pan-cáncer

| Método | Ruta | Función |
| --- | --- | --- |
| `POST` | `/pancancer/survival` | Enviar barrido TCGA reference |
| `GET` | `/pancancer/survival/{scan_id}` | Recuperar barrido TCGA reference |
| `GET` | `/pancancer/survival/{scan_id}/download/csv` | Descargar resultados TCGA reference |
| `GET` | `/pancancer/survival/{scan_id}/download/{kind}` | Descargar artefacto TCGA reference |
| `POST` | `/pancancer/hierarchical/preflight` | Inspeccionar elegibilidad jerárquica antes del cómputo |
| `POST` | `/pancancer/hierarchical-survival` | Enviar síntesis jerárquica TCGA + externos |
| `GET` | `/pancancer/hierarchical-survival/{scan_id}` | Recuperar una síntesis jerárquica completada |
| `GET` | `/pancancer/hierarchical-survival/{scan_id}/download/{kind}` | Descargar un artefacto jerárquico reproducible |
| `GET` | `/pancancer/immune-screens` | Listar pantallas inmunes |
| `GET` | `/pancancer/immune-screens/{screen_id}` | Recuperar una pantalla |
| `GET` | `/pancancer/immune-screens/{screen_id}/download/{kind}` | Descargar datos |

#### Modo TCGA reference

El contrato existente `/pancancer/survival` es el modo **TCGA reference**. Su
pipeline e identidad de caché continúan siendo
`server-attested-common-scale-reml-hksj-contract-v3.3`; agregar el análisis
jerárquico no reinterpreta, invalida ni recalcula silenciosamente sus
resultados. Sigue limitado a cohortes TCGA y conserva el esquema establecido
para solicitudes de un gen o una firma.

Artefactos TCGA reference: `patients`, `methodology`, `audit_json`, `audit_html`,
`attestation`, `raw_r_json`, `result_json` y `zip`. La ruta dedicada `csv`
entrega la tabla por cohorte.

El pipeline TCGA reference informa el efecto Cox de cada cohorte por una desviación
estándar de expresión dentro de ese cáncer como estimación descriptiva no
combinada. Para un gen o una firma mean/weighted también recupera el
coeficiente exacto por +1 unidad común del score de entrada y sintetiza
efectos comparables con efectos aleatorios REML, inferencia HKSJ e intervalo
de predicción del 95%. La síntesis exige un mismo endpoint y una misma familia
de modelo. No se combinan firmas z-score estandarizadas por cohorte, endpoints
mixtos ni efectos seleccionados de familias de ajuste distintas. Las
sensibilidades por estadio, grado y estadio+grado y el BH-FDR permanecen
separados por familia. La ausencia de covariables clínicas se marca
`not_evaluable`, no como fallo del modelo primario. La respuesta y el CSV por
cohorte exponen los campos descriptivos `hazard_ratio`, los campos de síntesis
`common_scale_*` y el contrato `effect_scale`.

#### Modo jerárquico TCGA + externos

El modo jerárquico es un flujo adicional dentro de Pan-cancer, no una nueva
sección de la aplicación ni un reemplazo del barrido TCGA reference. Se
versiona por separado como
`hierarchical-study-cancer-iqr-reml-mhksj-contract-v1.3`.

`POST /pancancer/hierarchical/preflight` es síncrono y no crea un trabajo de
cómputo. Aplica el registro versionado de universos y devuelve la solicitud
normalizada, versión del registro, universos elegibles y excluidos, soporte por
cáncer, advertencias y códigos de razón explícitos. La misma solicitud se
envía a `POST /pancancer/hierarchical-survival`, que crea un trabajo asíncrono
`pancancer_hierarchical`. Debe consultarse `/jobs/{job_id}` y luego seguir su
`result_url` o usar las rutas jerárquicas de resultado y descarga de la tabla.
Los valores `schema_version` de las respuestas son
`tcga-trace-hierarchical-pancancer-preflight-v1` y
`tcga-trace-hierarchical-pancancer-result-v1`, respectivamente.

El resumen del preflight distingue todos los cánceres representados de los
cánceres que tienen al menos dos clusters primarios de estudio independientes.
Expone `replicated_cancers`, `replicated_events`,
`preliminary_global_ready` y `formal_global_ready`; `can_run` todavía puede ser
verdadero cuando solo sea posible informar estimaciones descriptivas por
estudio o cáncer.

La solicitud mantiene un estimando primario deliberadamente acotado:

```json
{
  "gene_symbol": "MKI67",
  "scope": "combined",
  "cancers": [],
  "study_ids": [],
  "endpoint": "OS",
  "clinical_context": "primary_baseline",
  "time_origin_policy": "strict_baseline",
  "effect_scale": "within_study_iqr",
  "overlap_policy": "independent_clusters",
  "min_patients": 20,
  "min_events": 10,
  "min_censored": 5,
  "include_exploratory": false,
  "fdr_threshold": 0.05
}
```

`gene_symbol` se normaliza a mayúsculas y solo se acepta un gen. Los alias
históricos conocidos se resuelven una sola vez antes de seleccionar universos
TCGA o externos (por ejemplo, `P53` a `TP53` y `HER2` a `ERBB2`). El preflight
y el resultado conservan `requested_gene_symbol` y `resolved_gene_symbol`,
mientras solicitudes equivalentes por alias o símbolo canónico seleccionan el
mismo estimando y universos, pero reciben identidades de artefacto separadas.
Así, la provenance de una consulta no sobrescribe la de otra. Cada registro de
estudio también expone en `gene_mapping` el símbolo resuelto, identificador fuente, origen del mapeo e
índice de fila de expresión específico del release. El endpoint es sobrevida
global estricta (`OS`). `scope` puede ser `combined`, `tcga_only`
o `external_only`; listas vacías en `cancers` y `study_ids` indican todos los
universos compatibles con el registro dentro de ese alcance. El contexto
clínico se prespecifica como `primary_baseline`, `advanced_treatment` o
`hematologic_diagnostic`. Endpoint, clase de origen temporal, contexto clínico
y familia de modelo deben ser compatibles antes de integrar efectos en una
misma síntesis.

Cada cohorte TCGA o release externo conserva su propio universo analítico. El
servidor selecciona una muestra elegible con expresión completa por paciente,
ajusta un modelo Cox continuo por separado e informa el hazard ratio por un
aumento de +1 IQR calculado dentro de ese universo. Así se explicita la unidad
del coeficiente sin afirmar que los valores fuente fueron armonizados. Nunca
se concatenan matrices de expresión ni filas de pacientes entre estudios.

El registro conserva fuente, mapeo de cáncer, contexto clínico, origen
temporal, cluster de estudio/dependencia y solapamiento exacto o parcial
conocido. Los releases de un mismo cluster de dependencia no cuentan como
replicación independiente; una dependencia sin resolver o un contexto
incompatible permanece visible en el ledger de exclusiones del preflight en
vez de combinarse silenciosamente.

La identidad de caché jerárquica incorpora un SHA-256 canónico del registro de
universos, taxonomía de cáncer, todos los manifiestos de estudio —incluidos los
inactivos—, versiones de esquema/registro e identidades de los manifiestos de
releases publicados. Por ello, un cambio capaz de modificar agrupamiento,
contexto, origen temporal o datos fuente no puede reutilizar silenciosamente
un trabajo completado anterior. El preflight es síncrono y se recalcula en
cada solicitud.

Los log hazard ratios elegibles se sintetizan con efectos aleatorios siguiendo
una jerarquía declarada: evidencia de estudios dentro de cada cáncer y luego
estimaciones de cáncer en el resultado pan-cáncer global. REML estima la
heterogeneidad y HKSJ modificado provee la inferencia de intervalos con la
regla `max(1, q)`, que impide que su error estándar sea menor que el error
estándar convencional de efectos aleatorios. El resultado conserva para
auditoría la escala no modificada y si se aplicó el piso. Los resultados
exponen efectos por estudio, cáncer y global, intervalos de predicción del 95%
cuando son estimables, estadísticas de heterogeneidad y sensibilidades
leave-one-study/cancer-out. Los p por estudio son descriptivos; BH-FDR se
aplica únicamente a la familia de efectos de cáncer replicados por al menos dos
clusters de estudio independientes. Un cáncer con un solo estudio permanece
descriptivo y no recibe FDR. Se requieren al menos dos cánceres replicados para
estimar el efecto global. El soporte pan-cáncer formal exige además al menos
cinco cánceres replicados y 100 eventos OS entre sus estudios primarios. El
estimado global constituye una síntesis declarada.

El soporte primario exige por universo al menos 20 pacientes, 10 eventos OS y
5 pacientes censurados. Si `include_exploratory` está habilitado, los universos
con al menos 10 pacientes, 5 eventos y 5 censurados pueden aparecer en un nivel
exploratorio rotulado por separado; no pasan silenciosamente a contar como
replicación primaria. Las exclusiones del preflight, fallas de ajuste y soporte
independiente insuficiente permanecen en el ledger devuelto.

Este modo no produce una curva Kaplan--Meier global. Esa curva mezclaría
baselines y orígenes temporales propios de cada estudio e implicaría una
cohorte de pacientes agrupada que el análisis no crea. Los tipos de descarga
jerárquica son `studies`, `cancers`, `ledger`, `methodology`, `audit_json`,
`audit_html`, `attestation`, `result_json` y `zip`; la respuesta completada
enumera los enlaces disponibles en `downloads`.

El atlas inmune versionado aplica a escala masiva el mismo contrato de modelo
primario más sensibilidad ordinal. El BH-FDR gen-cáncer y el meta-FDR por gen
se calculan por separado para las familias primaria, estadio+grado, estadio y
grado. La jerarquía seleccionada por disponibilidad permite resumir retención,
atenuación, emergencia y cambios de dirección, pero nunca combina por
meta-análisis familias seleccionadas diferentes.

Descargas de pantalla inmune: `genes`, `cohorts`, `terms`, `results`, `panel`,
`manifest` y `methodology`. Atlas v2 también expone `gene_models`,
`cohort_models`, `term_models`, `sensitivity`, `audit`, `family_summary`,
`raw_results` y `zip`.

Todas las rutas de las tablas son relativas a la base REST v1. El documento
OpenAPI publicado es la fuente autoritativa para los esquemas.

## Errores

Los errores v1 tienen una envoltura estable:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request did not match the documented API contract.",
    "details": {},
    "request_id": "4ea1..."
  }
}
```

Se puede enviar `X-Request-ID` para correlación; en caso contrario el servidor
lo genera. Debe respetarse `Retry-After` en respuestas `429` y `503`. Los
límites se asocian a la dirección de red verificada por el proxy, por lo que
investigadores de una misma red institucional pueden compartir la cuota.
`HOURLY_LIMIT` indica que se alcanzó la cuota móvil de una hora para esa familia;
`CLIENT_ACTIVE_LIMIT`, que esa red ya tiene cinco trabajos activos; y
`QUEUE_FULL`, que la capacidad global está temporalmente completa. El valor de
`Retry-After` informa la espera restante, no una nueva hora completa.

## Límites y retención de la beta

- Dos análisis se ejecutan simultáneamente en todo el despliegue.
- La cola admite hasta 50 trabajos activos.
- Cada dirección de red puede mantener hasta cinco trabajos activos.
- Trabajos simples, combinados, de panel y GSEA: 25 envíos por tipo y dirección
  de red en cada hora móvil.
- Expression Comparison: 1.000 envíos por dirección de red en cada hora móvil.
  Sigue aplicándose el límite separado de cinco trabajos activos por red.
- Lotes: dos envíos por dirección de red en cada hora móvil, con un máximo de 25 análisis.
- Robustness (familia API `multiverse`): un envío por dirección de red en cada hora móvil, con un máximo de 72
  especificaciones.
- Pan-cáncer: dos envíos por dirección de red en cada hora móvil.
- Exportaciones de sesión: cinco envíos por cliente y hora, con hasta 200
  eventos seleccionados.
- Los resultados públicos se conservan 90 días. Los privados, incluidos los
  informes de sesión, usan el plazo privado de 24 horas y se eliminan junto
  con su dataset. Los trabajos activos protegen sus datos privados del
  vencimiento hasta terminar.
- Reenviar una solicitud vencida regenera sus artefactos.

Cada envío aceptado que requiere ejecución cuenta para el límite de la hora
móvil, también al reintentar un trabajo fallido. Recuperar un trabajo idéntico
en cola, en ejecución o completado y vigente no consume otro envío. REST y MCP
usan la misma regla. Un intento antiguo no puede modificar el estado, el
resultado ni la señal de actividad del intento vigente.

El proxy también limita ráfagas HTTP. Es suficiente consultar un trabajo cada
dos segundos; una frecuencia mayor no acelera el cómputo.

## Conectar ChatGPT

El endpoint usa Streamable HTTP y no requiere OAuth en la beta pública.

1. Activar Developer mode en la configuración de conectores/apps de ChatGPT.
2. Crear una app o conector personalizado desde un servidor MCP remoto.
3. Ingresar `https://apps.cienciavida.org/tcga_explorer/mcp`.
4. Seleccionar la opción sin autenticación.
5. Revisar las herramientas descubiertas y habilitar el conector en el chat.

Los administradores pueden restringir conectores personalizados; los controles
disponibles dependen del plan y de la política del workspace.

## Conectar Claude

1. Abrir la configuración de conectores de Claude.
2. Agregar un conector remoto personalizado.
3. Ingresar `https://apps.cienciavida.org/tcga_explorer/mcp`.
4. Completar la conexión sin autenticación.
5. Habilitar TRACE Explorer y pedir primero la lista de cohortes o
   datasets curados antes de analizar.

La disponibilidad depende del plan de Claude y de la política organizacional.

## Herramientas MCP

Descubrimiento:

- `trace_list_tcga_cohorts`
- `trace_list_cancer_types`
- `trace_list_datasets`
- `trace_list_dataset_candidates`
- `trace_get_dataset`
- `trace_get_dataset_endpoints`
- `trace_list_dataset_expression_layers`
- `trace_resolve_dataset_gene`
- `trace_search_dataset_genes`
- `trace_get_tcga_dataset_summary`
- `trace_list_survival_endpoints`
- `trace_get_tcga_cohort_endpoints`
- `trace_list_expression_scales`
- `trace_list_gsea_collections`
- `trace_get_tcga_filter_options`
- `trace_get_dataset_filter_options`
- `trace_search_tcga_genes`
- `trace_resolve_tcga_gene`

`trace_list_tcga_cohorts` conserva su nombre por compatibilidad. Ahora devuelve
cohortes TCGA y cohortes registradas sólo como externas; el cliente debe leer el
campo `status` y no deducir que una cohorte pertenece a TCGA a partir del nombre
de la herramienta. Para releases externas, las herramientas específicas de
dataset siguen siendo la fuente autoritativa.

Cómputo y resultados:

- `trace_run_survival_analysis`
- `trace_run_combined_analysis`
- `trace_run_signature_panel`
- `trace_run_gsea_analysis`
- `trace_run_expression_comparison`
- `trace_run_batch_analysis`
- `trace_run_robustness_analysis`
- `trace_run_pancancer_analysis`
- `trace_preflight_hierarchical_pancancer`
- `trace_run_hierarchical_pancancer_analysis`
- `trace_get_job`
- `trace_get_analysis`
- `trace_list_immune_screens`
- `trace_get_immune_screen`

`trace_preflight_hierarchical_pancancer` devuelve un ledger de elegibilidad
sincrónico y acotado con los campos explícitos `total`, `returned` y
`truncated`. Si está truncado, se debe revisar el preflight REST completo antes
de la síntesis jerárquica. Las demás herramientas de cómputo devuelven un
trabajo; el modelo debe usar
`trace_get_job` hasta que finalice y conservar advertencias, procedencia del
endpoint, conteos de pacientes/eventos, diagnósticos, heterogeneidad y contexto
de pruebas múltiples al interpretar. Para datasets externos curados y datasets
privados `user-*` autorizados, se deben usar
`trace_get_dataset_endpoints`, `trace_list_dataset_expression_layers`,
`trace_get_dataset_filter_options` y `trace_resolve_dataset_gene` antes de
construir un request de cómputo. En conjunto exponen los contratos de endpoint,
capa de expresión, agrupación/filtros y resolución génica de cada release.

Un dataset privado debe cargarse primero por la web o el endpoint REST
multipart. Antes de usar su ID en MCP debe configurarse
`X-TRACE-Dataset-Token` (o un token Bearer) en el transporte. Luego puede usarse
en `trace_get_dataset`,
`trace_get_dataset_endpoints`, `trace_list_dataset_expression_layers`,
`trace_get_dataset_filter_options`, `trace_search_dataset_genes`,
`trace_resolve_dataset_gene` y los requests de cómputo compatibles. La creación
del upload, su borrado manual y la
exportación de sesiones exploratorias no son herramientas MCP; para esas
operaciones con estado se usa web/REST. MCP entrega respuestas compactas con
enlaces al resultado REST completo y sus artefactos.

Recursos de solo lectura:

- `trace-explorer://dataset/version`
- `trace-explorer://methods`

## Citación y uso responsable

Al usar endpoints clínicos TCGA, citar:

> Liu J, et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive
> High-Quality Survival Outcome Analytics. *Cell*. 2018;173:400-416.e11.
> doi:10.1016/j.cell.2018.02.052.

También debe citarse la versión de datos GDC/TCGA pertinente y conservar la
versión del pipeline, fechas de datos, payload, ID de análisis, advertencias y
checksum de auditoría proporcionados por TRACE Explorer.

## Cliente de linea de comandos

El cliente Python sin dependencias `scripts/tcga_trace_cli.py` consume el mismo
contrato v1 y OpenAPI. Incluye descubrimiento, las familias de cómputo
establecidas, consulta de trabajos persistentes, descarga recursiva de batches
y verificacion de bundles.

```bash
python3 scripts/tcga_trace_cli.py contract-check
python3 scripts/tcga_trace_cli.py run analysis request.json \
  --artifacts zip --download-dir resultados/run-1 --verify
```

Consulta [la guia completa del CLI](CLI_ES.md). La verificacion respeta el
alcance de integridad declarado; un hash no firmado no se convierte en una
atestacion de terceros.

Las rutas históricas `/api/*` se mantienen temporalmente por compatibilidad. Las
integraciones nuevas deben usar `/api/v1/*`.
