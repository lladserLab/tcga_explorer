TEX_IMAGE ?= texlive/texlive:latest
PDF_NAME := tcga_explorer_bioinformatics_app_note.pdf
SUPPLEMENT_PDF_NAME := tcga_explorer_bioinformatics_supplement.pdf

.PHONY: pdf supplement all clean

pdf:
	mkdir -p build
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex && cp build/main.pdf build/$(PDF_NAME)'

supplement:
	mkdir -p build
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build supplementary.tex && cp build/supplementary.pdf build/$(SUPPLEMENT_PDF_NAME)'

all: pdf supplement

clean:
	rm -rf build
