import re
import json
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


class ImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> str:
        return "python:3.7-slim"
    
    def image_prefix(self) -> str:
        return "envagent"
       
    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
        return [
            File(
                ".",
                "fix.patch",
                f"{self.pr.fix_patch}",
            ),
            File(
                ".",
                "test.patch",
                f"{self.pr.test_patch}",
            ),
            File(
                ".",
                "prepare.sh",
                """ls -la
###ACTION_DELIMITER###
pip install --upgrade pip setuptools wheel
###ACTION_DELIMITER###
apt-get update && apt-get install -y build-essential
###ACTION_DELIMITER###
pip install .[dev,test,louvain,leiden,magic,scvi,harmony,skmisc,scrublet,scanorama]
###ACTION_DELIMITER###
echo 'MPLBACKEND=Agg pytest --ignore=scanpy/tests/_images -rA -v' > /home/scanpy/test_commands.sh && chmod +x /home/scanpy/test_commands.sh
###ACTION_DELIMITER###
bash /home/scanpy/test_commands.sh
###ACTION_DELIMITER###
pip show get-version
###ACTION_DELIMITER###
pip install get_version==3.3.0
###ACTION_DELIMITER###
bash /home/scanpy/test_commands.sh
###ACTION_DELIMITER###
pip show legacy-api-wrap
###ACTION_DELIMITER###
pip install get_version==2.0.0
###ACTION_DELIMITER###
bash /home/scanpy/test_commands.sh
###ACTION_DELIMITER###
pip install importlib-metadata
###ACTION_DELIMITER###
pip show umap-learn
###ACTION_DELIMITER###
pip install umap-learn==0.5.3
###ACTION_DELIMITER###
bash /home/scanpy/test_commands.sh"""
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
MPLBACKEND=Agg pytest --ignore=scanpy/tests/_images -rA -v

""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
if ! git -C /home/{pr.repo} apply --whitespace=nowarn /home/test.patch; then
    echo "Error: git apply failed" >&2
    exit 1  
fi
MPLBACKEND=Agg pytest --ignore=scanpy/tests/_images -rA -v

""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
if ! git -C /home/{pr.repo} apply --whitespace=nowarn  /home/test.patch /home/fix.patch; then
    echo "Error: git apply failed" >&2
    exit 1  
fi
MPLBACKEND=Agg pytest --ignore=scanpy/tests/_images -rA -v

""".format(
                    pr=self.pr
                ),
            ),
        ]

    def dockerfile(self) -> str:
        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        dockerfile_content = """
# This is a template for creating a Dockerfile to test patches
# LLM should fill in the appropriate values based on the context

# Choose an appropriate base image based on the project's requirements - replace [base image] with actual base image
# For example: FROM ubuntu:**, FROM python:**, FROM node:**, FROM centos:**, etc.
FROM python:3.7-slim

## Set noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Install basic requirements
# For example: RUN apt-get update && apt-get install -y git
# For example: RUN yum install -y git
# For example: RUN apk add --no-cache git
RUN apt-get update && apt-get install -y git

# Ensure bash is available
RUN if [ ! -f /bin/bash ]; then         if command -v apk >/dev/null 2>&1; then             apk add --no-cache bash;         elif command -v apt-get >/dev/null 2>&1; then             apt-get update && apt-get install -y bash;         elif command -v yum >/dev/null 2>&1; then             yum install -y bash;         else             exit 1;         fi     fi

WORKDIR /home/
COPY fix.patch /home/
COPY test.patch /home/
RUN git clone https://github.com/scverse/scanpy.git /home/scanpy

WORKDIR /home/scanpy
RUN git reset --hard
RUN git checkout {pr.base.sha}
"""
        dockerfile_content += f"""
{copy_commands}
"""
        return dockerfile_content.format(pr=self.pr)


@Instance.register("scverse", "scanpy_1_8_0_dev0")
class SCANPY_1_8_0_DEV0(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return ImageDefault(self.pr, self._config)

    def run(self, run_cmd: str = "") -> str:
        if run_cmd:
            return run_cmd

        return 'bash /home/run.sh'

    def test_patch_run(self, test_patch_run_cmd: str = "") -> str:
        if test_patch_run_cmd:
            return test_patch_run_cmd

        return "bash /home/test-run.sh"

    def fix_patch_run(self, fix_patch_run_cmd: str = "") -> str:
        if fix_patch_run_cmd:
            return fix_patch_run_cmd

        return "bash /home/fix-run.sh"


    def parse_log(self, log: str) -> TestResult:
        # Parse the log content and extract test execution results.
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()
        import re
        import json
        # Patterns for test results
        # PASSED: scanpy/tests/test_binary.py::test_builtin_settings PASSED
        passed_pattern = re.compile(r'^(.*?) PASSED')
        # FAILED: scanpy/tests/test_plotting.py::test_genes_symbols[stacked_violin-stacked_violin] FAILED
        failed_pattern = re.compile(r'^(?:FAILED )?(.*?)(?: FAILED| - |$)')
        # SKIPPED: scanpy/tests/test_datasets.py::test_burczynski06 SKIPPED
        skipped_pattern = re.compile(r'^(.*?) SKIPPED')
        for line in log.splitlines():
            # Passed tests
            m = passed_pattern.match(line)
            if m and '::' in m.group(1):
                passed_tests.add(m.group(1).strip())
                continue
            # Failed tests
            if line.startswith('FAILED '):
                m = failed_pattern.match(line)
                if m and '::' in m.group(1):
                    failed_tests.add(m.group(1).strip())
                    continue
            elif line.endswith(' FAILED') and '::' in line:
                # Inline failed test
                test_name = line[:line.rfind(' FAILED')].strip()
                failed_tests.add(test_name)
                continue
            # Skipped tests (only lines with '::' in test name)
            m = skipped_pattern.match(line)
            if m and '::' in m.group(1):
                skipped_tests.add(m.group(1).strip())
                continue
        parsed_results = {
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests
        }
        

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
