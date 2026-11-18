# Third-party notices and dependency inventory

## Scope and method

This inventory is derived from the repository's `requirements.txt`,
`requirements.lock`, `web/package.json`, and `web/package-lock.json`. License
names below are copied from the local package metadata in the npm lock file;
they are not inferred. If a package metadata entry did not provide a license,
it would be recorded as **Unknown**. The lockfile entries listed here provide a
license field. This is informational documentation, not legal advice; all
licensing and distribution questions are **to be verified by qualified counsel
against official sources**.

**Official-source verification:** unavailable; no official-source verification
was performed.

## Project license status

No project-level `LICENSE` file or project license declaration was found in the
repository inventory. The web package is marked `private` and does not declare
a license. The project license is therefore **Unknown / not selected**. Do not
infer a project license from the licenses of its dependencies. See
`docs/LICENSE_DECISION.md`.

## Python runtime

* `.python-version` pins Python **3.11.9**.
* `requirements.txt` states that CareLoop uses only the Python standard library
  for offline reproducibility.
* `requirements.lock` is intentionally empty and states that there are no
  third-party runtime dependencies.
* The standard library is part of Python and is not inventoried here as a
  separately vendored third-party package. Python distribution terms are not
  asserted by this document.

The README mentions FastAPI and Uvicorn as optional accelerators, and
DATA_SOURCES.md notes that PyYAML is optional for general YAML input. None of
these packages is declared in the requirements files or the inspected npm
metadata. Their versions, installed status, and licenses are therefore
**Unknown from repository metadata** and are outside the locked runtime
inventory.

The Dockerfile uses the Python 3.11.9 slim base image. The base-image license,
provenance, and distribution obligations are not inventoried in the repository
metadata reviewed here and are **Unknown** pending a separate image review.

## Direct web package dependencies

Versions are the exact declarations in `web/package.json` and the root entry of
`web/package-lock.json`; licenses are the package-lock metadata values.

| Package | Version | Section | License in local metadata |
| --- | ---: | --- | --- |
| `@vitejs/plugin-react` | 4.3.4 | dependency | MIT |
| `react` | 19.0.0 | dependency | MIT |
| `react-dom` | 19.0.0 | dependency | MIT |
| `typescript` | 5.7.2 | dependency | Apache-2.0 |
| `vite` | 6.0.5 | dependency | MIT |
| `@types/react` | 19.0.8 | devDependency | MIT |
| `@types/react-dom` | 19.0.3 | devDependency | MIT |

## Transitive and optional lockfile packages

The following are package entries in `web/package-lock.json`, including
optional platform-specific entries. A package with the same version and license
is grouped to keep this notice readable. The exact dependency graph remains in
the lock file.

### MIT

* `@babel/code-frame` 7.29.7; `@babel/compat-data` 7.29.7;
  `@babel/core` 7.29.7; `@babel/generator` 7.29.8;
  `@babel/helper-compilation-targets` 7.29.7; `@babel/helper-globals` 7.29.7;
  `@babel/helper-module-imports` 7.29.7; `@babel/helper-module-transforms` 7.29.7;
  `@babel/helper-plugin-utils` 7.29.7; `@babel/helper-string-parser` 7.29.7;
  `@babel/helper-validator-identifier` 7.29.7;
  `@babel/helper-validator-option` 7.29.7; `@babel/helpers` 7.29.10;
  `@babel/parser` 7.29.9; `@babel/plugin-transform-react-jsx-self` 7.29.7;
  `@babel/plugin-transform-react-jsx-source` 7.29.7;
  `@babel/template` 7.29.7; `@babel/traverse` 7.29.10; `@babel/types` 7.29.8.
* `@esbuild/aix-ppc64`, `@esbuild/android-arm`, `@esbuild/android-arm64`,
  `@esbuild/android-x64`, `@esbuild/darwin-arm64`, `@esbuild/darwin-x64`,
  `@esbuild/freebsd-arm64`, `@esbuild/freebsd-x64`, `@esbuild/linux-arm`,
  `@esbuild/linux-arm64`, `@esbuild/linux-ia32`, `@esbuild/linux-loong64`,
  `@esbuild/linux-mips64el`, `@esbuild/linux-ppc64`, `@esbuild/linux-riscv64`,
  `@esbuild/linux-s390x`, `@esbuild/linux-x64`, `@esbuild/netbsd-x64`,
  `@esbuild/openbsd-arm64`, `@esbuild/openbsd-x64`, `@esbuild/sunos-x64`,
  `@esbuild/win32-arm64`, `@esbuild/win32-ia32`, and `@esbuild/win32-x64`,
  each 0.24.0.
* `@jridgewell/gen-mapping` 0.3.13; `@jridgewell/remapping` 2.3.5;
  `@jridgewell/resolve-uri` 3.1.2; `@jridgewell/sourcemap-codec` 1.6.0;
  `@jridgewell/trace-mapping` 0.3.31; `@napi-rs/lzma-linux-x64-gnu` 1.5.1.
* `@rollup/rollup-android-arm-eabi`, `@rollup/rollup-android-arm64`,
  `@rollup/rollup-darwin-arm64`, `@rollup/rollup-darwin-x64`,
  `@rollup/rollup-freebsd-arm64`, `@rollup/rollup-freebsd-x64`,
  `@rollup/rollup-linux-arm-gnueabihf`, `@rollup/rollup-linux-arm-musleabihf`,
  `@rollup/rollup-linux-arm64-gnu`, `@rollup/rollup-linux-arm64-musl`,
  `@rollup/rollup-linux-loong64-gnu`, `@rollup/rollup-linux-loong64-musl`,
  `@rollup/rollup-linux-ppc64-gnu`, `@rollup/rollup-linux-ppc64-musl`,
  `@rollup/rollup-linux-riscv64-gnu`, `@rollup/rollup-linux-riscv64-musl`,
  `@rollup/rollup-linux-s390x-gnu`, `@rollup/rollup-linux-x64-gnu`,
  `@rollup/rollup-linux-x64-musl`, `@rollup/rollup-openbsd-x64`,
  `@rollup/rollup-openharmony-arm64`, `@rollup/rollup-win32-arm64-msvc`,
  `@rollup/rollup-win32-ia32-msvc`, `@rollup/rollup-win32-x64-gnu`, and
  `@rollup/rollup-win32-x64-msvc`, each 4.64.10.
* `@types/babel__core` 7.20.5; `@types/babel__generator` 7.27.0;
  `@types/babel__template` 7.4.4; `@types/babel__traverse` 7.28.0;
  `@types/estree` 1.0.9; `@vitejs/plugin-react` 4.3.4;
  `browserslist` 4.29.4; `convert-source-map` 2.0.0; `debug` 4.4.3;
  `esbuild` 0.24.0; `escalade` 3.2.0; `fsevents` 2.3.3;
  `gensync` 1.0.0-beta.2; `js-tokens` 4.0.0; `jsesc` 3.1.0;
  `json5` 2.2.3; `ms` 2.1.3; `nanoid` 3.3.20; `node-releases` 2.0.59;
  `postcss` 8.5.31; `react` 19.0.0; `react-dom` 19.0.0;
  `react-refresh` 0.14.2; `rollup` 4.64.10; `scheduler` 0.25.0;
  `update-browserslist-db` 1.3.4; and `vite` 6.0.5.

### Apache-2.0

* `baseline-browser-mapping` 2.11.30
* `typescript` 5.7.2

### CC-BY-4.0

* `caniuse-lite` 1.0.30001816 (the nested Browserslist lockfile entry)

### BSD-3-Clause

* `source-map-js` 1.2.2

### ISC

* `electron-to-chromium` 1.5.459; `lru-cache` 5.1.1;
  `picocolors` 1.1.1; `semver` 6.3.1; `yallist` 3.1.1

## Review notes

The inventory records metadata, not a legal conclusion about compatibility,
attribution, notice placement, patents, trademarks, source distribution, or
base-image obligations. Those questions are informational and **to be verified
by qualified counsel against official sources**. The CareLoop trademark was not
checked.
