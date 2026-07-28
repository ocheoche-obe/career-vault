# careervault-weasyprint layer — WeasyPrint + its native runtime libraries (ADR-023 / ADR-018).
#
# Built by SAM (BuildMethod: makefile) inside the Amazon Linux 2023 python3.13 build container, so
# the shared objects match the Lambda arm64 runtime — always build this stack with
# `sam build --use-container`. WeasyPrint 60+ needs **Pango** (text layout) and its dependency
# closure (glib, harfbuzz, fribidi, freetype, fontconfig, …); it no longer uses Cairo or
# gdk-pixbuf, which keeps the closure small. Lambda automatically puts /opt/lib on LD_LIBRARY_PATH;
# the resume_agent function sets FONTCONFIG_PATH=/opt/fonts and XDG_CACHE_HOME=/tmp (fontconfig's
# cache must live on a writable path).
#
# Fallback (ADR-023): if this build ever proves blocking, swapping to a public Klayers WeasyPrint
# layer is a two-line template change.

# The libraries WeasyPrint's cffi bindings dlopen by name (see WeasyPrint's text/ffi.py). We copy
# these plus their full ldd closure, minus the glibc set the Lambda runtime already provides.
CORE_LIBS = libgobject-2.0.so.0 libpango-1.0.so.0 libpangoft2-1.0.so.0 libharfbuzz.so.0 libfontconfig.so.1

build-WeasyPrintLayer:
	# 1. WeasyPrint + Python deps into the layer's python/ dir (lands at /opt/python).
	python -m pip install --no-cache-dir -r requirements.txt -t "$(ARTIFACTS_DIR)/python"

	# 2. System libraries. Install Pango + fontconfig + a font, then copy the dependency closure of
	#    the core libs, skipping anything glibc provides (copying those would risk an ABI clash).
	dnf install -y --setopt=install_weak_deps=False pango fontconfig dejavu-sans-fonts >/dev/null
	mkdir -p "$(ARTIFACTS_DIR)/lib"
	for lib in $(CORE_LIBS); do \
	  path=$$(find /usr/lib64 -name "$$lib" | head -n1); \
	  [ -n "$$path" ] && ldd "$$path"; \
	done | awk '/=> \// {print $$3}' | sort -u | while read -r so; do \
	  case "$$so" in \
	    */libc.so*|*/libm.so*|*/libpthread.so*|*/libdl.so*|*/librt.so*|*/ld-linux*|*/libresolv.so*) ;; \
	    *) cp -Lv "$$so" "$(ARTIFACTS_DIR)/lib/" ;; \
	  esac; \
	done
	# ldd lists dependencies, not the targets themselves — copy the core libs (and their sonames) too.
	for lib in $(CORE_LIBS); do \
	  find /usr/lib64 -name "$$lib*" -exec cp -Lv {} "$(ARTIFACTS_DIR)/lib/" \; ; \
	done

	# 3. Fonts + a minimal fontconfig config that points at them and caches to /tmp.
	mkdir -p "$(ARTIFACTS_DIR)/fonts"
	find /usr/share/fonts -name '*.ttf' -exec cp {} "$(ARTIFACTS_DIR)/fonts/" \;
	printf '%s\n' \
	  '<?xml version="1.0"?>' \
	  '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">' \
	  '<fontconfig>' \
	  '  <dir>/opt/fonts</dir>' \
	  '  <cachedir>/tmp/fontconfig</cachedir>' \
	  '  <config></config>' \
	  '</fontconfig>' > "$(ARTIFACTS_DIR)/fonts/fonts.conf"
