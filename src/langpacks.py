# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Representation of the langpacs service."""

import logging
import ops
import os
import shutil

import charms.operator_libs_linux.v0.apt as apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

from launchpadlib.launchpad import Launchpad
from pathlib import Path
from subprocess import check_call, check_output, CalledProcessError

logger = logging.getLogger(__name__)

# Packages installed as part of the update process.
PACKAGES = ["build-essential", "libgettextpo-dev", "debhelper", "fakeroot", "python3-launchpadlib", "python3-apt", "dput", "git", "devscripts", "lintian"]

HOME = Path("~ubuntu").expanduser()
REPO_LOCATION = HOME / "langpack-o-matic"

class Langpacks:
    """Represent a langpacks instance in the workload."""

    def __init__(self):
        logger.debug("Langpacks class init")

    def setup_crontab(self):
        """Configure the crontab for the service"""
        try:
            check_call(
                [
                    "su",
                    "-c",
                    f"crontab src/crontab",
                    "ubuntu",
                ]
            )
            return
        except CalledProcessError as e:
            logger.debug(
                "Installation of the crontab failed with return code %d", e.returncode
            )
            return

    def install(self):
        """Install the langpack builder environment"""

        # Install the deb packages needed for the service
        try:
            apt.update()
        except CalledProcessError as e:
            logger.error("failed to update package cache: %s", e)
            raise

        for p in PACKAGES:
            try:
                apt.add_package(p)
            except PackageNotFoundError:
                logger.error("failed to find package %s in package cache", p)
                raise
            except PackageError as e:
                logger.error("failed to install %s: %s", p, e)
                raise

        # Clone the langpack-o-matic repo
        try:
            check_call(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "git",
                    "clone",
                    "-b",
                    "master",
                    "https://git.launchpad.net/langpack-o-matic",
                    REPO_LOCATION,
                ]
            )
        except CalledProcessError as e:
            logger.debug(
                "Git clone of the code failed with return code %d", e.returncode
            )
            return

    def update_checkout(self):
        """Update the langpack-o-matic checkout"""

        # Pull Vcs updates
        try:
            check_call(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "git",
                    "-C",
                    REPO_LOCATION,
                    "pull",
                ]
            )
        except CalledProcessError as e:
            logger.debug(
                "Git pull of the code failed with return code %d", e.returncode
            )
            return

        # Call make target
        try:
            check_call(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "make",
                    "-C",
                    REPO_LOCATION / "bin",
                ]
            )
        except CalledProcessError as e:
            logger.debug(
                "Build of msgequal failed with return code %d", e.returncode
            )
            return

    def build_langpacks(self, base, release):
        """Build the langpacks"""

        lp = Launchpad.login_anonymously("langpacks", "production")
        ubuntu = lp.distributions['ubuntu']

        # check that the series used is valid
        active_series = []
        for s in ubuntu.series:
          if s.active == True:
            active_series.append(s.name)

        release = release.lower()
        devel_series = ubuntu.getDevelopmentSeries()[0].name
        if release == "devel":
          release = devel_series

        if release not in active_series:
          logger.debug(f"Release {release} isn't an active Ubuntu series")
          return

        if base == True:

          BUILDDIR = HOME / release
          if not os.path.exists(BUILDDIR):
            # Create target directory
            try:
              check_call(
                  [
                      "sudo",
                      "-u",
                      "ubuntu",
                      "mkdir",
                      HOME / release,
                  ]
                )
            except CalledProcessError as e:
                logger.debug(
                    "Creating directory failed with return code %d", e.returncode
                )
                return
          else:
            # Or clear existing cache directories before starting
            for builddir in (BUILDDIR / "sources-base", BUILDDIR / "sources-update"):
              if os.path.exists(builddir):
                try:
                  shutil.rmtree(builddir)
                  logger.debug("Removed the existing cache directory: %s", builddir)
                except OSError as e:
                  logger.error("Failed to remove cache directory %s: %s", builddir, e)

          # Download the current translations tarball from launchpad
          try:
              check_call(
                  [
                      "sudo",
                      "-u",
                      "ubuntu",
                      "wget",
                      "--no-check-certificate",
                      "-q",
                      "-O",
                      REPO_LOCATION / f"ubuntu-{release}-translations.tar.gz",
                      f"https://translations.launchpad.net/ubuntu/{release}/+latest-full-language-pack",
                  ]
              )
          except CalledProcessError as e:
              logger.debug(
                  "Download of the tarball failed with return code %d", e.returncode
              )
              return

          # Call the import script that prepares the packages
          try:
              check_call(
                  [
                      "sudo",
                      "-u",
                      "ubuntu",
                      REPO_LOCATION / "import",
                      "-v",
                      "--treshold=10",
                      REPO_LOCATION / f"ubuntu-{release}-translations.tar.gz",
                      release,
                      HOME / release,
                  ]
              )
          except CalledProcessError as e:
              logger.debug(
                  "Building the langpacks source failed with return code %d", e.returncode
              )
              return
        else:
          # TODO: build -updates variant of the langpacks
          print("Build updates")

    def upload_langpacks(self):
          """Upload the packages"""
          try:
              check_call(
                  [
                      "sudo",
                      "-u",
                      "ubuntu",
                      REPO_LOCATION / "packages",
                      "upload",
                  ],
                  cwd=REPO_LOCATION
              )
          except CalledProcessError as e:
              logger.debug(
                  "Building the langpacks source failed with return code %d", e.returncode
              )
              return

    def disable_crontab(self):
        try:
            check_call(
                [
                    "su",
                    "-c",
                    "crontab -r",
                    "ubuntu",
                ]
            )
            return
        except CalledProcessError as e:
            logger.debug(
                "Disabling of crontab failed with return code %d", e.returncode
            )
            return
