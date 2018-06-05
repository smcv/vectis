ACLOCAL_AMFLAGS = -I m4

CLEANFILES =

BUILT_SOURCES = \
	${top_srcdir}/.version \
	${NULL}

EXTRA_DIST = \
	${dist_uninstalled_test_scripts} \
	${nodist_bin_SCRIPTS:=.in} \
	${top_srcdir}/.version \
	.gitignore \
	autogen.sh \
	build-aux/COPYING.GPL-3 \
	build-aux/git-version-gen \
	run \
	${NULL}

nobase_dist_pkgdata_DATA = \
	vectis/__init__.py \
	vectis/__main__.py \
	vectis/apt.py \
	vectis/autopkgtest.py \
	vectis/commands/__init__.py \
	vectis/commands/autopkgtest.py \
	vectis/commands/bootstrap.py \
	vectis/commands/lxc_tarballs.py \
	vectis/commands/minbase_tarball.py \
	vectis/commands/new.py \
	vectis/commands/piuparts.py \
	vectis/commands/run.py \
	vectis/commands/sbuild.py \
	vectis/commands/sbuild_tarball.py \
	vectis/config.py \
	vectis/debuild.py \
	vectis/defaults.yaml \
	vectis/error.py \
	vectis/keys/buildd.debian.org_archive_key_2017_2018.gpg \
	vectis/lxc.py \
	vectis/piuparts.py \
	vectis/util.py \
	vectis/worker.py \
	${NULL}

nobase_dist_pkgdata_SCRIPTS = \
	vectis/setup-testbed \
	vectis/vectis-command-wrapper \
	${NULL}

nodist_bin_SCRIPTS = \
	scripts/vectis \
	${NULL}
CLEANFILES += ${nodist_bin_SCRIPTS}

scripts/vectis: scripts/vectis.in Makefile
	@${MKDIR_P} scripts
	${AM_V_GEN}${SED} \
		-e 's#[@]pkgdatadir[@]#${pkgdatadir}#g' \
		< $< > $@-t && chmod 0755 $@-t && mv $@-t $@

AM_TESTS_ENVIRONMENT = \
	export PYTHONPATH=$(abs_top_srcdir); \
	export VECTIS_UNINSTALLED=$(abs_top_srcdir); \
	${NULL}

TEST_EXTENSIONS = .py .sh .t

PY_LOG_COMPILER = ${PYTHON}

LOG_DRIVER = env \
	AM_TAP_AWK='$(AWK)' \
	$(SHELL) \
	$(top_srcdir)/build-aux/tap-driver.sh
PY_LOG_DRIVER = $(LOG_DRIVER)
SH_LOG_DRIVER = $(LOG_DRIVER)
T_LOG_DRIVER = $(LOG_DRIVER)

installed_testdir = ${libexecdir}/installed-tests/${PACKAGE_TARNAME}
installed_test_metadir = ${datadir}/installed-tests/${PACKAGE_TARNAME}

dist_test_scripts = \
	t/config.py \
	t/debian/autopkgtest.t \
	t/debian/bootstrap.t \
	t/debian/new.t \
	t/debian/sbuild_tarball.t \
	t/ubuntu/new.t \
	${NULL}

# Only run one of the slow tests at a time, otherwise we'll tend to
# run out of memory to run all the necessary VMs
t/debian/bootstrap.log: t/debian/autopkgtest.log
t/debian/new.log: t/debian/bootstrap.log
t/debian/sbuild_tarball.log: t/debian/new.log
t/ubuntu/new.log: t/debian/sbuild_tarball.log

dist_test_extra_scripts = \
	t/__init__.py \
	${NULL}

nobase_dist_installed_test_SCRIPTS = \
	${dist_test_scripts} \
	${dist_test_extra_scripts} \
	${NULL}

dist_uninstalled_test_scripts = \
	t/mypy.sh \
	t/pycodestyle.sh \
	t/pyflakes.sh \
	t/shellcheck.sh \
	${NULL}

nobase_installed_test_meta_DATA = \
	${dist_test_scripts:=.test} \
	${NULL}

TESTS = \
	${dist_test_scripts} \
	${dist_uninstalled_test_scripts} \
	${NULL}

installcheck-local:
	PATH='${DESTDIR}${bindir}'"$${PATH:+":$$PATH"}"; \
	export PATH; \
	PYTHONPATH='${DESTDIR}${pkgdatadir}'"$${PYTHONPATH:+":$$PYTHONPATH"}"; \
	export PYTHONPATH; \
	VECTIS_DESTDIR='${DESTDIR}'; \
	export VECTIS_DESTDIR; \
	: $${XDG_DATA_DIRS:=/usr/local/share:/usr/share}; \
	XDG_DATA_DIRS='${DESTDIR}${datadir}:'"$$XDG_DATA_DIRS"; \
	export XDG_DATA_DIRS; \
	gnome-desktop-testing-runner \
		--dir='${DESTDIR}${datadir}' \
		--parallel=1 \
		--timeout=1000 \
		vectis

$(nobase_installed_test_meta_DATA): %.test: % Makefile
	@$(MKDIR_P) "$$(dirname "$@")"
	$(AM_V_GEN) ( \
		echo '[Test]'; \
		echo 'Type=session'; \
		echo 'Output=TAP'; \
		echo 'Exec=sh -c '"'"'$${VECTIS_DESTDIR}$(installed_testdir)/$*'"'"; \
	) > $@.tmp && mv $@.tmp $@
CLEANFILES += $(nobase_installed_test_meta_DATA)

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

uninstall-local: uninstall-local-pycache
uninstall-local-pycache:
	rm -fr $(DESTDIR)$(pkgdatadir)/vectis/__pycache__
	rm -fr $(DESTDIR)$(pkgdatadir)/vectis/commands/__pycache__
.PHONY: uninstall-local-pycache
