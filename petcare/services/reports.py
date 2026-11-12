"""Persist the exact preview bytes without leaving a partially written report."""
from pathlib import Path
from tempfile import NamedTemporaryFile


def save_report(destination, payload, file_format):
    if file_format not in {"csv", "json"}:
        raise ValueError("Есеп пішімі CSV немесе JSON болуы керек.")
    path = Path(destination)
    if not path.suffix:
        path = path.with_suffix("." + file_format)
    if path.suffix.casefold() != "." + file_format:
        raise ValueError(f"Файл атауы .{file_format} деп аяқталуы керек.")
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
        temporary.replace(path)
    except OSError as exc:
        raise ValueError("Файл сақталмады. Таңдалған орынға жазу мүмкіндігін тексеріңіз.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
