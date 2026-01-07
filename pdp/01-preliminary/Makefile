MAIN = report

BIBTEX = bibtex
LATEX = pdflatex
LATEX_OPTS = -shell-escape

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex bibliography.bib
	$(LATEX) $(LATEX_OPTS) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(LATEX_OPTS) $(MAIN)
	$(LATEX) $(LATEX_OPTS) $(MAIN)

clean:
	@rm -f *~ *.aux *.log *.bbl *.blg *.vrb *.toc *.nav *.out *.snm;
	@rm -fr $(MAIN).pdf;
	@rm -fr auto _minted*;

help:
	@echo "Makefile usage :"
	@echo "- make [all]\tbuild the specifications"
	@echo "- make clean\terase useless files"
	@echo "- make help\tdisplay this help"

.PHONY: all clean help
