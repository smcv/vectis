ACLOCAL_AMFLAGS = -I m4

CLEANFILES = \
	${NULL}

EXTRA_DIST = \
	${dist_uninstalled_test_scripts} \
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
	vectis/error.py \
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

AM_TESTS_ENVIRONMENT = \
	export PYFLAKES=${PYFLAKES}; \
	export PYTHONPATH=$(abs_top_srcdir); \
	${NULL}

LOG_DRIVER = env \
	AM_TAP_AWK='$(AWK)' \
	$(SHELL) \
	$(top_srcdir)/build-aux/tap-driver.sh

installed_testdir = ${libexecdir}/installed-tests/${PACKAGE_TARNAME}
installed_test_metadir = ${datadir}/installed-tests/${PACKAGE_TARNAME}

dist_test_scripts = \
	t/config.py \
	${NULL}

dist_test_extra_scripts = \
	t/__init__.py \
	t/manual/bootstrap.t \
	t/manual/new.t \
	t/manual/sbuild_tarball.t \
	${NULL}

nobase_dist_installed_test_SCRIPTS = \
	${dist_test_scripts} \
	${dist_test_extra_scripts} \
	${NULL}

dist_uninstalled_test_scripts = \
	t/pyflakes.sh \
	${NULL}

TESTS = \
	${dist_test_scripts} \
	${dist_uninstalled_test_scripts} \
	${NULL}

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
