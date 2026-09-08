"""Deterministic Meta configuration, without changing the process environment."""

import io
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import click
from dotenv.parser import Binding, parse_stream


class EnvironmentFileError(click.ClickException):
    """Safe errors that never include file contents or candidate credentials."""


@dataclass(frozen=True)
class ResolvedValue:
    value: str | None = field(repr=False)
    source: str | None = None


def get_env_file_path() -> Path:
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / 'pyproject.toml').is_file() and (checkout / 'common/src/kulturbytes_common').is_dir():
        return checkout / '.env'
    config_home = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    if not config_home.is_absolute():
        config_home = Path.home() / '.config'
    return config_home / 'kulturbytes-social/.env'


def _read_text(path: Path) -> str:
    try:
        if path.is_symlink():
            raise EnvironmentFileError('.env darf kein symbolischer Link sein.')
        with path.open(encoding='utf-8', newline='') as stream:
            return stream.read()
    except FileNotFoundError:
        return ''
    except (OSError, UnicodeError):
        raise EnvironmentFileError('.env konnte nicht gelesen werden.') from None


def _bindings(text: str) -> list[Binding]:
    bindings = list(parse_stream(io.StringIO(text)))
    if any(binding.error for binding in bindings):
        raise EnvironmentFileError('.env enthält eine ungültige Zuweisung.')
    return bindings


def read_env_file() -> dict[str, str | None]:
    # Parse literal values: no shell evaluation or ${...} interpolation of secrets.
    return {item.key: item.value for item in _bindings(_read_text(get_env_file_path())) if item.key is not None}


def get_dotenv_value(name: str) -> str | None:
    return read_env_file().get(name)


def get_config(name: str, default: str = '') -> str:
    values = read_env_file()
    if name in values:
        return values[name] or ''
    return os.environ.get(name, default)


def _inline_comment(binding: Binding) -> str:
    """Keep a target binding's trailing comment when replacing its value."""
    raw = binding.original.string.strip()
    tail = raw.split('=', 1)[1].lstrip() if '=' in raw else raw[len(binding.key or ''):]
    if tail.startswith(("'", '"')):
        quote = tail[0]
        index = 1
        while index < len(tail):
            if tail[index] == '\\':
                index += 2
                continue
            if tail[index] == quote:
                tail = tail[index + 1:]
                break
            index += 1
        match = re.search(r'#.*', tail)
    else:
        match = re.search(r'(?:^|\s)(#.*)', tail)
    return match.group().lstrip() if match else ''


def set_dotenv_value(name: str, value: str) -> None:
    """Atomically replace one key, retaining unrelated bindings and comments."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) or '\x00' in value:
        raise EnvironmentFileError('Ungültiger .env-Schlüssel oder Wert.')
    path = get_env_file_path()
    temporary = None
    try:
        text = _read_text(path)
        bindings = _bindings(text)
        newline = '\r\n' if '\r\n' in text else '\n'
        quoted = "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
        replacement = f'{name}={quoted}{newline}'
        output = []
        replaced = False
        for item in bindings:
            if item.key != name:
                output.append(item.original.string)
                continue
            # python-dotenv includes preceding blank lines in the binding.
            prefix = re.match(r'\s*', item.original.string).group()
            output.append(prefix)
            comment = _inline_comment(item)
            if not replaced:
                output.append(f'{name}={quoted}' + (' ' + comment if comment else '') + newline)
                replaced = True
            elif comment:
                output.append(comment + newline)
        if not replaced:
            if text and not text.endswith(('\n', '\r')):
                output.append(newline)
            output.append(replacement)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix='.env.', suffix='.tmp', dir=path.parent)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            if os.name == 'posix':
                os.fchmod(stream.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            stream.write(''.join(output))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, UnicodeError):
        raise EnvironmentFileError('.env konnte nicht sicher gespeichert werden; Veröffentlichung abgebrochen.') from None
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def secure_env_file() -> None:
    """Tighten the validated local credential file without rewriting its contents."""
    if os.name != 'posix':
        return
    path = get_env_file_path()
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise EnvironmentFileError('.env kann nicht sicher mit restriktiven Rechten verwaltet werden.')
        path.chmod(0o600)
    except OSError:
        raise EnvironmentFileError('.env-Dateirechte konnten nicht gesichert werden.') from None
