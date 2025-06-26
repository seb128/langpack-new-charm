# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Representation of the langpacs service."""

import logging
import os
import shutil
from pathlib import Path
from subprocess import PIPE, STDOUT, CalledProcessError, run

import charms.operator_libs_linux.v0.apt as apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from launchpadlib.launchpad import Launchpad

logger = logging.getLogger(__name__)

# Packages installed as part of the update process.
PACKAGES = [
    "build-essential",
    "libgettextpo-dev",
    "debhelper",
    "fakeroot",
    "python3-launchpadlib",
    "python3-apt",
    "dput",
    "git",
    "devscripts",
    "lintian",
]

HOME = Path("~ubuntu").expanduser()
REPO_LOCATION = HOME / "langpack-o-matic"


class Langpacks:
    """Represent a langpacks instance in the workload."""

    def __init__(self):
        logger.debug("Langpacks class init")

    def setup_crontab(self):
        """Configure the crontab for the service."""
        try:
            run(
                [
                    "su",
                    "-c",
                    "crontab src/crontab",
                    "ubuntu",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            return
        except CalledProcessError as e:
            logger.debug(f"Installation of the crontab failed: {e.stdout}")
            raise

    def install(self):
        """Install the langpack builder environment."""
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
            run(
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
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
        except CalledProcessError as e:
            logger.debug(f"Git clone of the code failed: {e.stdout}")
            raise

    def update_checkout(self):
        """Update the langpack-o-matic checkout."""
        # Pull Vcs updates
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "git",
                    "-C",
                    REPO_LOCATION,
                    "pull",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
        except CalledProcessError as e:
            logger.debug(f"Git pull of the langpack-o-matic repository failed: {e.stdout}")
            raise

        # Call make target
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "make",
                    "-C",
                    REPO_LOCATION / "bin",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
        except CalledProcessError as e:
            logger.debug(f"Build of msgequal failed: {e.stdout}")
            raise

    def _clean_builddir(self, releasedir):
        for builddir in (
            releasedir / "sources-base",
            releasedir / "sources-update",
        ):
            if os.path.exists(builddir):
                try:
                    shutil.rmtree(builddir)
                    logger.debug("Removed the existing cache directory: %s", builddir)
                except OSError as e:
                    logger.error("Failed to remove cache directory %s: %s", builddir, e)

    def build_langpacks(self, base, release):
        """Build the langpacks."""
        lp = Launchpad.login_anonymously("langpacks", "production")
        ubuntu = lp.distributions["ubuntu"]

        # check that the series used is valid
        active_series = []
        for s in ubuntu.series:
            if s.active:
                active_series.append(s.name)

        release = release.lower()
        devel_series = ubuntu.getDevelopmentSeries()[0].name
        if release == "devel":
            release = devel_series

        if release not in active_series:
            logger.debug(f"Release {release} isn't an active Ubuntu series")
            return

        if base:
            releasedir = HOME / release
            if not os.path.exists(releasedir):
                # Create target directory
                try:
                    run(
                        [
                            "sudo",
                            "-u",
                            "ubuntu",
                            "mkdir",
                            HOME / release,
                        ],
                        check=True,
                        stdout=PIPE,
                        stderr=STDOUT,
                        text=True,
                    )
                except CalledProcessError as e:
                    logger.debug(f"Creating directory failed: {e.stdout}")
                    raise
            else:
                # Or clear existing cache directories before starting
                self._clean_builddir(releasedir)

            # Download the current translations tarball from launchpad
            try:
                run(
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
                    ],
                    check=True,
                    stdout=PIPE,
                    stderr=STDOUT,
                    text=True,
                )
            except CalledProcessError as e:
                logger.debug(f"Downloading the tarball failed: {e.stdout}")
                raise

            # Call the import script that prepares the packages
            try:
                run(
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
                    ],
                    check=True,
                    stdout=PIPE,
                    stderr=STDOUT,
                    text=True,
                )
            except CalledProcessError as e:
                logger.debug(f"Building the langpacks source failed: {e.stdout}")
                raise
        else:
            # TODO: build -updates variant of the langpacks
            print("Build updates")

    def upload_langpacks(self):
        """Upload the packages."""
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    REPO_LOCATION / "packages",
                    "upload",
                ],
                cwd=REPO_LOCATION,
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
        except CalledProcessError as e:
            logger.debug(f"Uploading the langpacks failed: {e.stdout}")
            raise

    def disable_crontab(self):
        """Disable the crontab."""
        try:
            run(
                [
                    "su",
                    "-c",
                    "crontab -r",
                    "ubuntu",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            return
        except CalledProcessError as e:
            logger.debug(f"Disabling of crontab failed: {e.stdout}")
            raise

    def import_gpg_key(self, key):
        """Import the private gpg key."""
        try:
            response = run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "gpg",
                    "--import",
                ],
                check=True,
                input=key,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug(f"GPG key imported: {response.stdout}")
        except CalledProcessError as e:
            logger.debug(f"Importing key failed: {e.stdout}")
            raise
