"""Replace one class in an existing Spring Boot jar without replacing other fixes."""
import hashlib
from pathlib import Path
import sys
import zipfile


CLASS = "BOOT-INF/classes/com/khc/u2/Util/QbApiUtil.class"


def patch_jar(source, destination, replacement):
    source, destination, replacement = map(Path, (source, destination, replacement))
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("Destination must be a new file, separate from the original jar")
    data = replacement.read_bytes()
    if not data.startswith(b"\xca\xfe\xba\xbe"):
        raise ValueError("Replacement is not a Java class")
    with zipfile.ZipFile(source) as original:
        if original.namelist().count(CLASS) != 1:
            raise ValueError("Expected exactly one QbApiUtil.class in the original jar")
        with zipfile.ZipFile(destination, "x") as patched:
            patched.comment = original.comment
            for entry in original.infolist():
                # Preserve compression (especially STORED nested jars) and entry metadata.
                patched.writestr(entry, data if entry.filename == CLASS else original.read(entry))
    verify_jar(destination, replacement)


def verify_jar(jar, replacement):
    expected = Path(replacement).read_bytes()
    with zipfile.ZipFile(jar) as archive:
        if archive.namelist().count(CLASS) != 1 or archive.read(CLASS) != expected:
            raise ValueError("Class verification failed")
        bad = archive.testzip()
        if bad:
            raise ValueError("Corrupt jar entry: " + bad)
    print("QbApiUtil.class SHA256=" + hashlib.sha256(expected).hexdigest())


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--verify":
        verify_jar(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4:
        patch_jar(*sys.argv[1:])
    else:
        raise SystemExit("Usage: patch_qb_api.py SOURCE DESTINATION CLASS | --verify JAR CLASS")
