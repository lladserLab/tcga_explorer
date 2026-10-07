"""Generate deterministic synthetic inputs for the unchanged bundled R scripts."""
import json
from pathlib import Path
import random
import struct
import sys

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
rng=random.Random(17291)
genes=[f'GENE{i:04}' for i in range(500)]
samples=[f'S{i:02}' for i in range(24)]
values=[rng.gauss(5,1)+(3 if gene<20 and sample>=12 else 0) for gene in range(500) for sample in range(24)]
(out/'matrix.f32').write_bytes(struct.pack('<'+str(len(values))+'f',*values))
base={'schema_version':'trace-bioconductor-signature-engine-v1','matrix_path':'Z:/fixture/matrix.f32','source_row_count':500,'source_sample_count':24,'source_endian':'little','gene_symbols':genes,'gene_row_indices_zero_based':list(range(500)),'sample_ids':samples,'sample_indices_zero_based':list(range(24)),'up_genes':genes[:20],'down_genes':[],'parameters':{'auc_max_rank':50},'sample_tie_seeds':list(range(100,124))}
for method,version in [('singscore','1.26.0'),('ssgsea','2.0.7'),('aucell','1.28.0')]:
 payload={**base,'method':method,'expected_package_version':version,'output_path':f'Z:/fixture/{method}-result.json'}
 (out/f'{method}.json').write_text(json.dumps(payload))
(out/'pathways.gmt').write_text('IMPLANTED\tsynthetic\t'+'\t'.join(genes[:20])+'\nCONTROL\tsynthetic\t'+'\t'.join(genes[100:120])+'\n')
camera={'matrix_path':'Z:/fixture/matrix.f32','output_path':'Z:/fixture/camera-result.json','gene_set_path':'Z:/fixture/pathways.gmt','genes':genes,'sample_ids':samples,'groups':['a']*12+['b']*12,'min_gene_set_size':10,'max_gene_set_size':100,'expected_limma_version':'3.62.2'}
(out/'camera.json').write_text(json.dumps(camera))
