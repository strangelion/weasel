# How to Rime with Weasel

## Preparation

  - Install **Visual Studio 2022** with *Desktop development with C++*,
    the **v143** toolset, **ATL/MFC**, and the **Windows 10 SDK 10.0.19041.0**
    to match CI. Include the ARM/ARM64 C++ tools and ATL/MFC components when
    building the ARM variants. The supported runtime is Windows 8.1 or later.

  - Install dev tools: `git`, `cmake`, `clang-format 18` (used by CI).

  - Download third-party libraries: `boost` (CI uses **1.84.0**).

Optional:

  - install `bash` via *Git for Windows*, for installing data files with `plum`;
  - install `python` for building OpenCC dictionaries;
  - install [NSIS](http://nsis.sourceforge.net/Download) for creating installer.

## Checkout source code

Make sure all git submodules are checked out recursively.

```batch
git clone --recursive https://github.com/rime/weasel.git
```

## Build and Install Weasel

Locate `weasel` source directory.

### Setup build environment

Edit your build environment settings in `env.bat`.
You can create the file by copying `env.bat.template` in the source tree.

Make sure `BOOST_ROOT` is set to the existing path `X:\path\to\boost_<version>`.

When using a different version of Visual Studio or platform toolset, un-comment
lines to set corresponding variables. For the CI toolchain, use
`env.vs2022.bat` as the starting point for `env.bat`.

Alternatively, start a *Developer Command Prompt* window and set environment
variables directly in the console, before invocation of `build.bat`:

```batch
set BOOST_ROOT=X:\path\to\boost_N_NN_N
```

### Build

```batch
cd weasel
build.bat all
```

Voila.

Installer will be generated in `output\archives` directory.

### Alternative: using prebuilt Rime binaries

If you've already got a copy of prebuilt binaries of librime, you can simply
copy `.dll`s / `.lib`s into `weasel\output` / `weasel\lib` directories
respectively, then build Weasel without the `all` command line option.

```batch
build.bat boost data opencc
build.bat weasel
```

### Run regression tests

After building with MSBuild, open a Visual Studio Developer PowerShell at the
repository root and run:

```powershell
.\test\run-tests.ps1 -Platform x64
.\test\run-tests.ps1 -Platform Win32
```

The script builds the Release test executable using the generated `weasel.props`
and existing Boost libraries. It tests response parsing and real named-pipe
communication in isolation, without connecting to the installed input method.
Each run has a 60-second timeout, returns a failure on build or test errors, and
saves logs under `msbuild/tests/<platform>`. Use `-PlatformToolset v143` to
override the toolset in `weasel.props` if needed.

The interactive `TestWeaselIPC` utility is separate and is not run by CI.

For an isolated comparison of an installed Rime grammar model, see
[the model benchmark guide](tools/README.md). This optional smoke test uses
existing model resources and does not change the installed input method.

### Build with GitHub Actions

The `CI` workflow in `.github/workflows/ci.yml` builds both MSBuild and xmake
variants. The MSBuild job also runs the x64 and Win32 regression tests before
uploading artifacts. After a successful run, open **Actions > CI > the run >
Artifacts** and download `weasel-artifact-*`; the archive contains the installer
and debug symbols. A fork may need to enable Actions first, and can also start
the workflow manually with **Run workflow**.

Automatic Release publishing is restricted to the upstream `rime/weasel`
repository by the workflow conditions; forks still receive build artifacts.

When packaging a local build without ARM components, pass
`/DWEASEL_X86_X64_ONLY` to `makensis`. This omits the optional ARM files and
rejects installation on ARM64 rather than installing incomplete components.

### Install and try it live

```batch
cd output
install.bat
```

### Optional: play with Rime command line tools

`librime` comes with a REPL application which can be used to test if the library
is working.

```batch
cd librime
copy /Y build\lib\Release\rime.dll build\bin
cd build\bin
echo zhongzhouyunshurufa | Release\rime_api_console.exe > output.txt
```

Instead of redirecting output to a file, you can set appropriate code page
(`chcp 65001`) and font in the console to work with the REPL interactively.
