#/***************************************************************************
# AutoQAD — CAD-style drawing tools for QGIS
#
# Copyright (C) 2026 Isaac Enage (byZenterra)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#***************************************************************************/

PLUGINNAME = autoqad

# Every new Python module and asset directory must be registered here AND in
# pb_tool.cfg, or it will not ship in the packaged zip.
PY_FILES = \
	__init__.py \
	main_plugin.py \
	controller.py \
	scripting.py

EXTRAS = metadata.txt icon.png LICENSE README.md install.py

EXTRA_DIRS = core engine input geom style commands ui io

SOURCES = $(PY_FILES)

LOCALES =

QGISDIR = .local/share/QGIS/QGIS3/profiles/default

default: compile

compile:
	@echo "AutoQAD builds its interface in code — nothing to compile."

# Syntax-check every module without needing QGIS.
check:
	python -c "import pathlib, py_compile, sys; \
	files=[f for f in pathlib.Path('.').rglob('*.py') if '__pycache__' not in str(f)]; \
	[py_compile.compile(str(f), doraise=True) for f in files]; \
	print('syntax OK:', len(files), 'files')"

# Run the pure-module tests — no QGIS required.
test-pure:
	python test/test_style.py
	python test/test_input.py
	python test/test_geom.py
	python test/test_engine.py
	python test/test_document_guard.py
	python test/test_flow_layout.py

# Run the full suite (needs a sourced QGIS environment).
test: compile
	@echo "----------------------------------------------"
	@echo "Running tests (requires QGIS on PYTHONPATH)"
	@echo "----------------------------------------------"
	PYTHONPATH=$(shell pwd) python -m pytest test/ -v

# Install into the QGIS profile.
#
# This delegates to install.py rather than using cp -r, deliberately. When the
# destination already exists, `cp -r src dest/` copies INTO it instead of over
# it, which silently produces a plugin tree nested inside one of its own
# subpackages — and an ImportError naming something that is plainly defined in
# the source. install.py removes the destination first and verifies the result.
deploy: compile
	python install.py

install: deploy

derase:
	python install.py --uninstall

zip: deploy clean
	rm -f $(PLUGINNAME).zip
	cd $(HOME)/$(QGISDIR)/python/plugins; zip -9r $(CURDIR)/$(PLUGINNAME).zip $(PLUGINNAME)

package: compile
	rm -f $(PLUGINNAME).zip
	git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(VERSION)
	@echo "Created package: $(PLUGINNAME).zip"

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

.PHONY: default compile check test-pure test deploy derase zip package clean
