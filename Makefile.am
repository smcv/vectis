ACLOCAL_AMFLAGS = -I m4

CLEANFILES = \
	${NULL}

EXTRA_DIST = \
	run \
	${NULL}

nobase_python_PYTHON = \
	vectis/__init__.py \
	vectis/__main__.py \
	vectis/commands/__init__.py \
	vectis/commands/bootstrap.py \
	vectis/commands/new.py \
	vectis/commands/sbuild.py \
	vectis/commands/sbuild_tarball.py \
	vectis/config.py \
	vectis/util.py \
	vectis/virt.py \
	${NULL}

nobase_python_SCRIPTS = \
	vectis/vectis-command-wrapper \
	${NULL}

nodist_bin_SCRIPTS = \
	scripts/vectis \
	${NULL}

scripts/vectis: scripts/vectis.in Makefile
	${AM_V_GEN}${SED} \
		-e 's#[@]pkgdatadir[@]#${pkgdatadir}#g' \
		< $< > $@-t && chmod 0755 $@-t && mv $@-t $@

@GENERATE_CHANGELOG_RULES@

.version:
	${AM_V_GEN}echo ${VERSION} > $@-t && mv $@-t $@

dist-hook: dist-ChangeLog

dist-hook: dist-hook-.tarball-version
dist-hook-.tarball-version:
	${AM_V_GEN}echo ${VERSION} > ${distdir}/.tarball-version
.PHONY: dist-hook-.tarball-version

clean-local: clean-local-pycache
clean-local-pycache:
	rm -fr vectis/__pycache__
	rm -fr vectis/commands/__pycache__
.PHONY: clean-local-pycache
