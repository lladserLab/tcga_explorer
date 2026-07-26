TEX_IMAGE ?= texlive/texlive@sha256:1a1b8588cd73ac33fe1d7722c4065b3e6eaa3f3a20fb54d2934e42310264d134
PDF_NAME := tcga-trace-bioinformatics-application-note.pdf
SUPPLEMENT_PDF_NAME := tcga-trace-bioinformatics-supplement.pdf
OUP_PDF_NAME := tcga-trace-bioinformatics-oup-preview.pdf

.PHONY: pdf supplement oup-preview compliance all clean

pdf:
	mkdir -p build
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex && cp build/main.pdf build/$(PDF_NAME)'

supplement:
	mkdir -p build
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build supplementary.tex && cp build/supplementary.pdf build/$(SUPPLEMENT_PDF_NAME)'

oup-preview:
	mkdir -p build
	../../scripts/publication/build_oup_preview.py
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build build/oup_preview.tex && cp build/oup_preview.pdf build/$(OUP_PDF_NAME)'

compliance: all
	../../scripts/publication/check_editorial_compliance.py

all: pdf supplement oup-preview

clean:
	rm -rf build
