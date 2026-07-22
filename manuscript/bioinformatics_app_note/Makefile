TEX_IMAGE ?= texlive/texlive:latest
PDF_NAME := tcga_explorer_bioinformatics_app_note.pdf

.PHONY: pdf clean

pdf:
	mkdir -p build
	docker run --rm -v "$$(pwd)":/work -w /work $(TEX_IMAGE) sh -lc 'latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex && cp build/main.pdf build/$(PDF_NAME)'

clean:
	rm -rf build
