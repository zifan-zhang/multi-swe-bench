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
        return "python:3.10-slim"
    
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
                """ls -al
###ACTION_DELIMITER###
cat .python-version
###ACTION_DELIMITER###
ls -al requirements
###ACTION_DELIMITER###
cat requirements/test.txt
###ACTION_DELIMITER###
cat requirements/main.txt
###ACTION_DELIMITER###
python3.5 --version
###ACTION_DELIMITER###
apt-get update
###ACTION_DELIMITER###
apt-get install -y python3.5 python3.5-dev
###ACTION_DELIMITER###
pyenv --version
###ACTION_DELIMITER###
apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev git
###ACTION_DELIMITER###
curl https://pyenv.run | bash
###ACTION_DELIMITER###
export PYENV_ROOT="$HOME/.pyenv" && export PATH="$PYENV_ROOT/bin:$PATH" && eval "$(pyenv init -)" && pyenv --version
###ACTION_DELIMITER###
pyenv install 3.5.3
###ACTION_DELIMITER###
pyenv local 3.5.3
###ACTION_DELIMITER###
python -m pip --version
###ACTION_DELIMITER###
python -m pip install --upgrade pip
###ACTION_DELIMITER###
apt-get install -y libpq-dev libhdf5-dev
###ACTION_DELIMITER###
python -m pip install -r requirements/test.txt
###ACTION_DELIMITER###
python -m pip install numpy
###ACTION_DELIMITER###
pyenv install 3.6.15
###ACTION_DELIMITER###
pyenv local 3.6.15
###ACTION_DELIMITER###
python -m pip install --upgrade pip
###ACTION_DELIMITER###
python -m pip install numpy
###ACTION_DELIMITER###
python -m pip install -r requirements/test.txt
###ACTION_DELIMITER###
echo 'python -m pytest --no-header -rA --tb=no -p no:cacheprovider src/tests/' > /home/triage/test_commands.sh
###ACTION_DELIMITER###
bash /home/triage/test_commands.sh
###ACTION_DELIMITER###
echo 'python -m pytest -rA --tb=no -p no:cacheprovider src/tests/' > /home/triage/test_commands.sh
###ACTION_DELIMITER###
bash /home/triage/test_commands.sh"""
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
python -m pytest -rA --tb=no -p no:cacheprovider src/tests/

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
python -m pytest -rA --tb=no -p no:cacheprovider src/tests/

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
python -m pytest -rA --tb=no -p no:cacheprovider src/tests/

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
FROM python:3.10-slim

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
RUN git clone https://github.com/dssg/triage.git /home/triage

WORKDIR /home/triage
RUN git reset --hard
RUN git checkout {pr.base.sha}
"""
        dockerfile_content += f"""
{copy_commands}
"""
        return dockerfile_content.format(pr=self.pr)


@Instance.register("dssg", "triage_v2_1_0")
class TRIAGE_V2_1_0(Instance):
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
        passed_tests = set() # Tests that passed successfully
        failed_tests = set() # Tests that failed
        skipped_tests = set() # Tests that were skipped
        import re
        import json
        # Implement the log parsing logic here
        # Pattern: <test_file.py> <results>
        test_line_re = re.compile(r'^(\S+\.py)\s+([.FsfS]+)$')
        for line in log.splitlines():
            m = test_line_re.match(line.strip())
            if m:
                test_file, results = m.groups()
                for idx, ch in enumerate(results, 1):
                    test_name = f"{test_file}::test_{idx}"
                    if ch == '.':
                        passed_tests.add(test_name)
                    elif ch in ('F',):
                        failed_tests.add(test_name)
                    elif ch in ('s', 'S'):
                        skipped_tests.add(test_name)
        # End of parsing logic
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
