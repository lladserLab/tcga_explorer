# Cliente de linea de comandos de TCGA-TRACE

`scripts/tcga_trace_cli.py` es un cliente Python sin dependencias para la API
REST v1 estable de TCGA-TRACE. Revisa el contrato OpenAPI en vivo, envia
trabajos persistentes, consulta su estado, descarga artefactos y verifica
bundles locales sin importar la aplicacion web ni el backend.

Se recomienda Python 3.10 o posterior.

## Inicio rapido

```bash
python3 scripts/tcga_trace_cli.py health
python3 scripts/tcga_trace_cli.py cohorts
python3 scripts/tcga_trace_cli.py genes TCGA-LIHC CDC --limit 10
python3 scripts/tcga_trace_cli.py contract-check
```

La API de produccion es el valor por defecto. Para usar el desarrollo local:

```bash
export TCGA_TRACE_API_URL=http://localhost:3000/tcga_explorer/
python3 scripts/tcga_trace_cli.py health
```

Tambien se puede pasar `--base-url`.

## Ejecutar un analisis

Guarda el request de la API en JSON:

```json
{
  "cohort": "TCGA-LIHC",
  "gene_symbol": "CDC20",
  "endpoint": "OS",
  "expression_scale": "log2_tpm",
  "cutpoint_method": "median",
  "adjustment_covariates": ["age_at_index"]
}
```

Enviar y retornar inmediatamente:

```bash
python3 scripts/tcga_trace_cli.py submit analysis request.json
```

Enviar, esperar, descargar y verificar:

```bash
python3 scripts/tcga_trace_cli.py run analysis request.json \
  --artifacts zip \
  --download-dir resultados/cdc20-lihc \
  --verify
```

Antes de enviar, `run` comprueba que el OpenAPI vivo contenga las operaciones
esperadas. `--skip-contract-check` debe reservarse para desarrollos conocidos
que sean compatibles.

## Familias de computo

| Familia CLI | Operacion REST | Contenido |
| --- | --- | --- |
| `analysis` | `POST /analyses` | Un gen o una firma |
| `combined` | `POST /analyses/combined` | Dos firmas independientes |
| `batch` | `POST /analyses/batch` | Hasta 25 analisis |
| `multiverse` | `POST /analyses/multiverse` | Grilla declarada de endpoint x score x corte |
| `pancancer` | `POST /pancancer/survival` | Barrido continuo entre cohortes |
| `session` | `POST /analyses/sessions/export` | Referencias terminales seleccionadas y anotaciones del navegador |

```bash
python3 scripts/tcga_trace_cli.py run combined combined.json --verify
python3 scripts/tcga_trace_cli.py run batch batch.json --verify
python3 scripts/tcga_trace_cli.py run multiverse multiverse.json --verify
python3 scripts/tcga_trace_cli.py run pancancer pancancer.json --verify
python3 scripts/tcga_trace_cli.py run session session-export.json --verify
```

Si se usa `--verify` sin `--artifacts`, el CLI descarga cada ZIP en
`tcga-trace-JOB_ID/`. En un batch recorre los resultados hijos y verifica cada
bundle completado.

## Retomar y descargar

```bash
python3 scripts/tcga_trace_cli.py job JOB_ID
python3 scripts/tcga_trace_cli.py job JOB_ID --wait

python3 scripts/tcga_trace_cli.py download JOB_ID \
  --download-dir resultados/JOB_ID \
  --artifacts zip \
  --verify
```

`--artifacts all` descarga todos los enlaces expuestos. El archivo
`tcga-trace-download-manifest.json` registra URL, bytes, SHA-256, resultado
logico y version del CLI.

## Verificacion local

```bash
python3 scripts/tcga_trace_cli.py verify resultados/JOB_ID
python3 scripts/tcga_trace_cli.py verify analysis.zip
python3 scripts/tcga_trace_cli.py verify analisis-descomprimido/
```

La verificacion reconoce cada familia:

- Analisis simple o combinado: hashes de pacientes, poblacion continua,
  scoring, resultado reproducible, artefactos y capsula.
- Multiverse: hash del request, hash de la familia declarada, sesion y numero
  de analisis hijos.
- Pan-cancer: hash reproducible y checksums de artefactos.
- Sesion exploratoria: hash de la seleccion, hash de familias definidas por el
  export, identidad del informe y numero de jobs fuente.
- Toda descarga: bytes y SHA-256 del manifiesto local.

Esto detecta deriva accidental, corrupcion, transferencias incompletas y
miembros ZIP inseguros. El origen servidor se verifica por separado. Cada
bundle nuevo de analisis, multiverse, pan-cancer o sesion exploratoria incluye
`attestation_receipt.json`. La clave exacta debe descargarse desde la URL HTTPS
declarada en el recibo y usarse para verificar la firma y los bytes del audit:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/attestation/keys/KEY_ID \
  > public-key.json

python3 scripts/verify_server_attestation.py \
  attestation_receipt.json audit_report.json \
  --key public-key.json
```

El recibo acredita que quien controla la clave publicada firmo ese informe
exacto. No demuestra correccion cientifica, no impide que el servidor firme
otro informe y no constituye un sello temporal inmutable.

## Descubrimiento

```text
index
health
cohorts
endpoints
expression-scales
cohort-endpoints COHORT
filters COHORT
genes COHORT [QUERY]
resolve COHORT QUERY
openapi
contract-check
```

Las respuestas usan JSON en stdout. El progreso y los errores estructurados se
escriben en stderr. `--output ARCHIVO` conserva la respuesta y `--compact`
produce JSON en una sola linea.

## Codigos de salida

| Codigo | Significado |
| --- | --- |
| `0` | Operacion o verificacion correcta |
| `2` | Error de argumentos, JSON o configuracion local |
| `3` | Error de red, HTTP o contrato API |
| `4` | Trabajo fallido, expirado o aun incompleto |
| `5` | Fallo de verificacion local |
| `6` | Se excedio `--wait-timeout` |

La API es la fuente autoritativa del esquema. Consulta `/api/openapi.json`,
Swagger o [la guia REST/MCP en espanol](API_ES.md) al construir nuevos
requests.
