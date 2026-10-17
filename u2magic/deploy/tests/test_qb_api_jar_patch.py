import importlib.util
from pathlib import Path
import zipfile

import pytest


spec = importlib.util.spec_from_file_location("patch_qb_api", Path(__file__).parents[1] / "patch_qb_api.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


def test_patch_preserves_other_fixes_and_nested_jar_compression(tmp_path):
    original, output, replacement = (tmp_path / name for name in ("old.jar", "new.jar", "QbApiUtil.class"))
    replacement.write_bytes(b"\xca\xfe\xba\xbeNEW")
    with zipfile.ZipFile(original, "w") as jar:
        jar.comment = b"existing manifest comment"
        jar.writestr(patcher.CLASS, b"OLD", compress_type=zipfile.ZIP_DEFLATED)
        jar.writestr("BOOT-INF/lib/dependency.jar", b"DEPENDENCY", compress_type=zipfile.ZIP_STORED)
        jar.writestr("BOOT-INF/classes/other.class", b"EXISTING FIX", compress_type=zipfile.ZIP_DEFLATED)
    before = original.read_bytes()
    patcher.patch_jar(original, output, replacement)
    assert original.read_bytes() == before
    with zipfile.ZipFile(output) as jar:
        assert jar.read(patcher.CLASS) == b"\xca\xfe\xba\xbeNEW"
        assert jar.read("BOOT-INF/classes/other.class") == b"EXISTING FIX"
        assert jar.read("BOOT-INF/lib/dependency.jar") == b"DEPENDENCY"
        assert jar.getinfo("BOOT-INF/lib/dependency.jar").compress_type == zipfile.ZIP_STORED
        assert jar.comment == b"existing manifest comment"


def test_missing_target_rejects_before_creating_output(tmp_path):
    original, output, replacement = (tmp_path / name for name in ("old.jar", "new.jar", "QbApiUtil.class"))
    replacement.write_bytes(b"\xca\xfe\xba\xbeNEW")
    with zipfile.ZipFile(original, "w") as jar:
        jar.writestr("unrelated.class", b"OLD")
    with pytest.raises(ValueError, match="exactly one"):
        patcher.patch_jar(original, output, replacement)
    assert not output.exists()


def test_patch_refuses_to_overwrite_the_original(tmp_path):
    original, replacement = tmp_path / "old.jar", tmp_path / "QbApiUtil.class"
    original.write_bytes(b"ORIGINAL")
    replacement.write_bytes(b"\xca\xfe\xba\xbeNEW")
    with pytest.raises(ValueError, match="separate"):
        patcher.patch_jar(original, original, replacement)
    assert original.read_bytes() == b"ORIGINAL"
