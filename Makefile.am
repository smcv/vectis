ACLOCAL_AMFLAGS = -I m4

CLEANFILES = \
	${nodist_bin_SCRIPTS} \
	${NULL}

BUILT_SOURCES = \
	${top_srcdir}/.version \
	${NULL}

EXTRA_DIST = \
	${dist_uninstalled_test_scripts} \
	${nodist_bin_SCRIPTS:=.in} \
	${top_srcdir}/.version \
	.gitignore \
	README.md \
	autogen.sh \
	build-aux/COPYING.GPL-3 \
	build-aux/git-version-gen \
	run \
	${NULL}

nobase_dist_pkgdata_DATA = \
	vectis/__init__.py \
	vectis/__main__.py \
	vectis/commands/__init__.py \
	vectis/commands/bootstrap.py \
	vectis/commands/new.py \
	vectis/commands/run.py \
	vectis/commands/sbuild.py \
	vectis/commands/sbuild_tarball.py \
	vectis/config.py \
	vectis/debuild.py \
	vectis/error.py \
	vectis/util.py \
	vectis/virt.py \
	${NULL}

nobase_dist_pkgdata_SCRIPTS = \
	vectis/vectis-command-wrapper \
	${NULL}

nodist_bin_SCRIPTS = \
	scripts/vectis \
	${NULL}

scripts/vectis: scripts/vectis.in Makefile
	@${MKDIR_P} scripts
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
	t/debian/bootstrap.t \
	t/debian/new.t \
	t/debian/sbuild_tarball.t \
	${NULL}

dist_test_extra_scripts = \
	t/__init__.py \
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

${top_srcdir}/.version:
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
