#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#


from setuptools import find_packages, setup

MAIN_REQUIREMENTS = [
    "airbyte-cdk~=0.1",
]

TEST_REQUIREMENTS = [
    "requests-mock~=1.9.3",
    "pytest~=6.1",
    "pytest-mock~=3.6.1",
    "responses~=0.13.3",
]

setup(
    entry_points={
        "console_scripts": [
            "source-pivotal-tracker=source_pivotal_tracker.run:run",
        ],
    },
    name="source_pivotal_tracker",
    description="Source implementation for Pivotal Tracker.",
    author="Airbyte",
    author_email="contact@airbyte.io",
    packages=find_packages(),
    install_requires=MAIN_REQUIREMENTS,
    package_data={"": ["*.json", "schemas/*.json", "schemas/shared/*.json"]},
    extras_require={
        "tests": TEST_REQUIREMENTS,
    },
)
