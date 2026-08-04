# Keep this file empty / side-effect-free.
#
# pyproject.toml reads the package version through
# `attr = "app.version.PEP440_VERSION"`, which imports this package during
# the build.  An import added here runs before dependencies are installed,
# so it would fail packaging metadata rather than the application.
