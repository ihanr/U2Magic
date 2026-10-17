"""Run real QbApiUtil/Hutool against loopback HTTP fixtures (no production access).

Set U2MAGIC_JAVA_HOME to a JDK 21 directory and U2MAGIC_APP_JAR to app.jar.
"""
import os
from pathlib import Path
import subprocess
import zipfile

import pytest


DEPLOY = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def java_checks(tmp_path_factory):
    java_home = os.environ.get("U2MAGIC_JAVA_HOME")
    app_jar = os.environ.get("U2MAGIC_APP_JAR")
    if not java_home or not app_jar:
        pytest.skip("Set U2MAGIC_JAVA_HOME and U2MAGIC_APP_JAR for Java integration checks")
    build = tmp_path_factory.mktemp("qb-api-java")
    with zipfile.ZipFile(app_jar) as jar:
        for name in jar.namelist():
            if name.startswith(("BOOT-INF/lib/", "BOOT-INF/classes/com/")) and not name.endswith("/"):
                jar.extract(name, build)
    output = build / "compiled"
    output.mkdir()
    classpath = os.pathsep.join((str(output), str(build / "BOOT-INF/classes"), str(build / "BOOT-INF/lib/*")))
    executable_suffix = ".exe" if os.name == "nt" else ""
    javac = Path(java_home) / "bin" / ("javac" + executable_suffix)
    java = Path(java_home) / "bin" / ("java" + executable_suffix)
    sources = [Path(__file__).with_name("QbApiCompatibilityCheck.java")]
    production = DEPLOY / "patch-src/com/khc/u2/Util/QbApiUtil.java"
    if production.exists() and not os.environ.get("U2MAGIC_TEST_BINARY"):
        sources.append(production)
    else:
        # Test the shipped binary before the fix exists, not a reimplementation.
        target = output / "com/khc/u2/Util/QbApiUtil.class"
        target.parent.mkdir(parents=True)
        target.write_bytes((DEPLOY / "jar-overrides/BOOT-INF/classes/com/khc/u2/Util/QbApiUtil.class").read_bytes())
    result = subprocess.run([str(javac), "-proc:none", "-encoding", "UTF-8", "--release", "21",
                             "-cp", classpath, "-d", str(output), *map(str, sources)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    return java, classpath, build


@pytest.mark.parametrize("scenario", [
    "legacy", "modern", "modern200", "cached", "stale", "no-cookie",
    "denied", "invalid-session", "multi", "add-legacy", "add-pending", "add-success",
    "add-json-failure", "add-forbidden", "add-html", "add-blank", "add-modern-cookie",
])
def test_qb_api_protocol(java_checks, scenario):
    java, classpath, build = java_checks
    result = subprocess.run([str(java), "-cp", classpath, "QbApiCompatibilityCheck",
                             scenario, str(build / scenario)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
