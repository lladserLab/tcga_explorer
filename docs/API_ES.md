# API pública y MCP de TCGA-TRACE

TCGA-TRACE publica sus flujos científicos actuales mediante una API REST y un
servidor remoto Model Context Protocol (MCP). Ambos usan la misma validación,
cola persistente de cómputo, caché y política de retención.

Los resultados son exploratorios. No están destinados a diagnóstico,
pronóstico, selección de tratamiento ni otras decisiones clínicas.

## Direcciones de producción

| Interfaz | Dirección |
| --- | --- |
| Aplicación web | `https://apps.cienciavida.org/tcga_explorer/` |
| API REST v1 | `https://apps.cienciavida.org/tcga_explorer/api/v1/` |
| Swagger UI | `https://apps.cienciavida.org/tcga_explorer/api/docs` |
| ReDoc | `https://apps.cienciavida.org/tcga_explorer/api/redoc` |
| OpenAPI 3 | `https://apps.cienciavida.org/tcga_explorer/api/openapi.json` |
| MCP remoto | `https://apps.cienciavida.org/tcga_explorer/mcp` |
| Guía en inglés | `https://apps.cienciavida.org/tcga_explorer/api/guide` |

`/tcga_explorer` es la ruta histórica estable de TCGA-TRACE y se conserva por
compatibilidad con marcadores y clientes API existentes; no es otro nombre del
producto.

La beta pública no requiere API key. Los límites se aplican a una identidad
anónima derivada de la IP verificada por el proxy o de la sesión MCP.

## Alcance científico y de datos

La API ofrece las mismas capacidades de datos públicos que la interfaz web:

- Resúmenes de cohortes, muestras, pacientes, genes, endpoints y fuentes TCGA.
- Releases curados de RNA-seq bulk independientes, con capas de expresión,
  definiciones de endpoint, licencia y manifiestos inmutables.
- Disponibilidad y control de calidad de OS, PFI, DFI y DSS.
- Análisis de gen único y firmas mean, z-score o ponderadas.
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
- Lotes acotados de comparaciones.
- Barridos Cox pan-cáncer continuos, BH-FDR, concordancia y metaanálisis.
- Pantallas inmunes pan-cáncer precalculadas.

El alcance público contiene datos abiertos derivados de TCGA/GDC, TCGA-CDR y
releases externos con licencia explícita. No expone rutas internas, manifiestos
de caché, controles de sincronización ni operaciones de base de datos. Una
matriz externa solo se puede descargar si el release permite redistribuirla.

Los artefactos de auditoría a nivel de paciente conservan los barcodes exactos
de participantes y muestras TCGA para trazabilidad científica. Aunque son
identificadores públicos de investigación, no deben usarse para intentar
reidentificar personas ni combinarse con datos restringidos.

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
| `GET` | `/cohorts/{cohort_id}/genes` | Buscar genes válidos |
| `GET` | `/cohorts/{cohort_id}/genes/resolve` | Resolver símbolo o alias |

### Repositorio curado de RNA-seq bulk externo

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/cancer-types` | Ledger de cobertura para los 33 tipos TCGA |
| `GET` | `/datasets` | Releases publicados de cohortes independientes |
| `GET` | `/datasets/{dataset_id}` | Fuente, licencia, QC, endpoints y capa de expresión |
| `GET` | `/datasets/{dataset_id}/endpoints` | Definiciones y QC de endpoints del release |
| `GET` | `/datasets/{dataset_id}/expression-layers` | Unidad, transformación y advertencias de escala |
| `GET` | `/datasets/{dataset_id}/filters` | Filtros clínicos curados disponibles |
| `GET` | `/datasets/{dataset_id}/genes` | Buscar genes en una capa fijada |
| `GET` | `/datasets/{dataset_id}/genes/resolve` | Resolver un gen en una capa fijada |
| `GET` | `/datasets/{dataset_id}/download/{kind}` | Descargar manifiesto, QC, licencia o matriz/metadata/genes autorizados |

Para analizar un release externo, el código TCGA conserva únicamente la
taxonomía del cáncer y se fijan dataset, release y capa:

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
expresión de TCGA. Los releases externos funcionan en Survival, Compare y
Multiverse; Pan-cancer continúa limitado a TCGA.

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
| `POST` | `/analyses/batch` | Enviar hasta 25 análisis |
| `POST` | `/analyses/multiverse` | Enviar una familia declarada de especificaciones |
| `POST` | `/analyses/sessions/export` | Exportar trabajos seleccionados como un registro exploratorio |
| `GET` | `/jobs/{job_id}` | Consultar cualquier trabajo |
| `GET` | `/analyses/{analysis_id}` | Recuperar un análisis |
| `GET` | `/analyses/batches/{batch_id}` | Recuperar un lote |
| `GET` | `/analyses/multiverses/{session_id}` | Recuperar una familia completada |
| `GET` | `/analyses/multiverses/{session_id}/download/{kind}` | Descargar artefacto de familia |
| `GET` | `/analyses/sessions/{report_id}` | Recuperar un registro exploratorio |
| `GET` | `/analyses/sessions/{report_id}/download/{kind}` | Descargar un artefacto de sesión |
| `GET` | `/analyses/{analysis_id}/download/{kind}` | Descargar artefacto |

Tipos de descarga de análisis: `zip`, `continuous_png`, `continuous_svg`,
`continuous_csv`, `png`, `svg`, `cox_png`, `cox_svg`,
`cumulative_incidence_png`, `cumulative_incidence_svg`, `csv`, `json`,
`audit_json`, `audit_html`, `attestation`, `txt` y `methodology`.

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
  `model` o `availability`) y `severity` (`info`, `caution` o
  `not_evaluable`).
- `diagnostics`: modelo clínico ajustado seleccionado, familia del modelo,
  estado superior (`clean`, `caution` o `not_evaluable`) y conteos de mensajes.

Solo una cautela diagnóstica del modelo ajustado seleccionado produce el estado
superior `caution`. La construcción de cohorte es información neutral, la
ausencia de un modelo ajustado es `not_evaluable` y las cautelas de modelos
auxiliares no contaminan el estado seleccionado. El arreglo histórico
`warnings` se conserva por compatibilidad; clientes nuevos deberían preferir
`notices` y `diagnostics`.

### Multiverso prespecificado

`POST /analyses/multiverse` recibe una cohorte, un gen o firma multigénica, uno
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

Tipos de descarga multiverse: `svg`, `csv`, `continuous_csv`, `ledger`, `json`,
`audit_json`, `audit_html`, `attestation`, `methodology` y `zip`.

### Historial exploratorio de sesión

`POST /analyses/sessions/export` acepta hasta 200 eventos seleccionados que
referencian valores `job_id` terminales, además de etiquetas y tiempos anotados
por el navegador. El servidor resuelve las solicitudes y resultados
autoritativos desde sus registros de cómputo. El informe no incorpora
registros por paciente ni valores de las filas de covariables externas.

BH y Bonferroni se aplican por separado a hipótesis únicas Cox continuas,
sensibilidades agrupadas por corte e interacciones de dos firmas. Las hipótesis
idénticas se cuentan una vez, aunque cada evento repetido permanece en el
ledger. Multiverse y pan-cáncer conservan su corrección interna y se listan
solo como referencias. El alcance es post hoc y depende de la selección
exportada: no prueba que no existan otras corridas ni genera un veredicto
retenido/no retenido.

Tipos de descarga: `json`, `runs_csv`, `hypotheses_csv`, `ledger`,
`audit_json`, `audit_html`, `attestation`, `methodology` y `zip`.

### Pan-cáncer

| Método | Ruta | Función |
| --- | --- | --- |
| `POST` | `/pancancer/survival` | Enviar barrido pan-cáncer |
| `GET` | `/pancancer/survival/{scan_id}` | Recuperar barrido |
| `GET` | `/pancancer/survival/{scan_id}/download/csv` | Descargar resultados |
| `GET` | `/pancancer/survival/{scan_id}/download/{kind}` | Descargar un artefacto reproducible |
| `GET` | `/pancancer/immune-screens` | Listar pantallas inmunes |
| `GET` | `/pancancer/immune-screens/{screen_id}` | Recuperar una pantalla |
| `GET` | `/pancancer/immune-screens/{screen_id}/download/{kind}` | Descargar datos |

Artefactos pan-cáncer: `patients`, `methodology`, `audit_json`, `audit_html`,
`attestation`, `raw_r_json`, `result_json` y `zip`. La ruta dedicada `csv`
entrega la tabla por cohorte.

El pipeline v2.8 informa el efecto Cox de cada cohorte por una desviación
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
lo genera. Debe respetarse `Retry-After` en respuestas `429` y `503`.

## Límites y retención de la beta

- Dos análisis se ejecutan simultáneamente en todo el despliegue.
- La cola admite hasta 50 trabajos activos.
- Cada cliente anónimo puede mantener hasta cinco trabajos activos.
- Trabajos simples y combinados: 10 envíos por tipo, cliente y hora.
- Lotes: dos envíos por cliente y hora, con un máximo de 25 análisis.
- Multiverse: un envío por cliente y hora, con un máximo de 72
  especificaciones.
- Pan-cáncer: dos envíos por cliente y hora.
- Exportaciones de sesión: cinco envíos por cliente y hora, con hasta 200
  eventos seleccionados.
- Los artefactos generados se conservan 90 días.
- Reenviar una solicitud vencida regenera sus artefactos.

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
5. Habilitar TCGA-TRACE y pedir primero la lista de cohortes antes de analizar.

La disponibilidad depende del plan de Claude y de la política organizacional.

## Herramientas MCP

Descubrimiento:

- `tcga_list_cohorts`
- `tcga_get_dataset_summary`
- `tcga_list_survival_endpoints`
- `tcga_get_cohort_endpoints`
- `tcga_list_expression_scales`
- `tcga_get_filter_options`
- `tcga_search_genes`
- `tcga_resolve_gene`

Cómputo y resultados:

- `tcga_run_survival_analysis`
- `tcga_run_combined_analysis`
- `tcga_run_batch_analysis`
- `tcga_run_pancancer_analysis`
- `tcga_get_job`
- `tcga_get_analysis`
- `tcga_list_immune_screens`
- `tcga_get_immune_screen`

Las herramientas de cómputo devuelven un trabajo. El modelo debe usar
`tcga_get_job` hasta que finalice y conservar advertencias, procedencia del
endpoint, conteos de pacientes/eventos, diagnósticos y contexto de pruebas
múltiples al interpretar. MCP entrega respuestas compactas con enlaces al
resultado REST completo y sus artefactos.

Recursos de solo lectura:

- `tcga-trace://dataset/version`
- `tcga-trace://methods`

## Citación y uso responsable

Al usar endpoints clínicos TCGA, citar:

> Liu J, et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive
> High-Quality Survival Outcome Analytics. *Cell*. 2018;173:400-416.e11.
> doi:10.1016/j.cell.2018.02.052.

También debe citarse la versión de datos GDC/TCGA pertinente y conservar la
versión del pipeline, fechas de datos, payload, ID de análisis, advertencias y
checksum de auditoría proporcionados por TCGA-TRACE.

## Cliente de linea de comandos

El cliente Python sin dependencias `scripts/tcga_trace_cli.py` consume el mismo
contrato v1 y OpenAPI. Incluye descubrimiento, las seis familias de computo,
consulta de trabajos persistentes, descarga recursiva de batches y
verificacion de bundles.

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
