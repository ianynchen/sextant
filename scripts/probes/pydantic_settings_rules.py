"""Pin pydantic-settings' environment-name and precedence rules (plan 3, Task 0).

Run it inside the orders-fastapi fixture's own environment, never Sextant's:

    fixtures/orders-fastapi/.venv/bin/python -I scripts/probes/pydantic_settings_rules.py

Every rule is asserted, then printed. The probe builds settings classes and sets environment
variables on purpose; Sextant itself never does (spec 7). Rules and quotes are in
`pydantic_settings_rules.md`.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import os
import tempfile
from pathlib import Path

from pydantic import AliasChoices, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

print(
    "versions:",
    {d: importlib.metadata.version(d) for d in ("pydantic", "pydantic-settings", "python-dotenv")},
)


def rule(text: str) -> None:
    print(f"RULE: {text}")


def clean() -> None:
    for k in [k for k in os.environ if k.upper().startswith(("APP_", "PORT", "DB_", "X_"))]:
        del os.environ[k]


tmp = Path(tempfile.mkdtemp())
os.chdir(tmp)
clean()


# 1. Env name = env_prefix + (validation_alias | alias | field name); the prefix is NOT applied to aliases.
class Plain(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")
    port: int = 1


os.environ["APP_PORT"] = "8"
assert Plain().port == 8
os.environ["PORT"] = "9"
assert Plain().port == 8  # un-prefixed name is not read
clean()


class Aliased(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")
    a: int = Field(1, alias="PORT_A")
    v: int = Field(1, validation_alias="PORT_V")
    both: int = Field(1, alias="PORT_X", validation_alias="PORT_Y")
    choices: int = Field(1, validation_alias=AliasChoices("PORT_C1", "PORT_C2"))


os.environ.update({"PORT_A": "2", "PORT_V": "3", "PORT_Y": "4", "PORT_C2": "5"})
s = Aliased()
assert (s.a, s.v, s.both, s.choices) == (2, 3, 4, 5)
clean()
os.environ.update({"APP_PORT_A": "7", "APP_PORT_V": "7", "APP_PORT_Y": "7", "APP_PORT_C1": "7"})
s = Aliased()
assert (s.a, s.v, s.both, s.choices) == (1, 1, 1, 1)  # prefix + alias is never read
clean()
os.environ.update({"APP_A": "7", "A": "7", "APP_V": "7", "V": "7"})
s = Aliased()
assert (s.a, s.v) == (
    1,
    1,
)  # the field name is NOT read once an alias exists (populate_by_name off)
clean()


class ByName(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", populate_by_name=True)
    a: int = Field(1, alias="PORT_A")


os.environ["APP_A"] = "7"
assert ByName().a == 7  # populate_by_name=True adds env_prefix + field name back
clean()
rule(
    "env name = env_prefix + field name; an alias/validation_alias REPLACES it and takes NO env_prefix "
    "(validation_alias wins over alias; field name is no longer read unless populate_by_name=True)"
)

os.environ.update({"PORT_C1": "1", "PORT_C2": "2"})
assert Aliased().choices == 1
clean()
rule("AliasChoices: choices tried in order, first present wins")


# 2. Case-insensitivity default.
class CI(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="app_")
    Port: int = 1


os.environ["APP_PORT"] = "8"
assert CI().Port == 8
clean()
os.environ["app_port"] = "6"
assert CI().Port == 6
clean()


class CS(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", case_sensitive=True)
    port: int = 1


os.environ["app_port"] = "3"
os.environ["APP_PORT"] = "4"
assert CS().port == 1  # case_sensitive: neither 'app_port' nor 'APP_PORT' is 'APP_port'
os.environ["APP_port"] = "2"
assert CS().port == 2
clean()
rule(
    "default case_sensitive=False: env_prefix, field name and env key compare case-insensitively; "
    "case_sensitive=True needs the exact 'env_prefix' + 'field name' spelling"
)

# 3. Precedence env > dotenv > default; env_file; missing file.
(tmp / ".env").write_text("APP_PORT=11\nAPP_OTHER=12\n")


class WithFile(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")
    port: int = 1
    other: int = 2
    third: int = 3


s = WithFile()
assert (s.port, s.other, s.third) == (11, 12, 3)  # dotenv over default
os.environ["APP_PORT"] = "21"
s = WithFile()
assert (s.port, s.other, s.third) == (21, 12, 3)  # env over dotenv over default
clean()
rule("precedence per field: environment variable > dotenv file > field default")


class Missing(BaseSettings):
    model_config = SettingsConfigDict(env_file="does-not-exist.env")
    port: int = 1


assert Missing().port == 1
rule("a missing env_file is silently ignored")

# env_file relative paths resolve against the process cwd, not the module.
sub = tmp / "sub"
sub.mkdir()
os.chdir(sub)
assert WithFile().port == 1
os.chdir(tmp)
assert WithFile().port == 11
rule("a relative env_file resolves against the process working directory at construction")

# env_file as a tuple: later files win.
(tmp / ".env.local").write_text("APP_PORT=31\n")


class Two(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=(".env", ".env.local"))
    port: int = 1
    other: int = 2


assert Two().port == 31
rule("env_file=(a, b): later files override earlier ones")

# dotenv keys: matched case-insensitively; a key no field names is an extra input.
(tmp / ".env2").write_text("app_port=41\n")


class Extra(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env2")
    port: int = 1


assert Extra().port == 41
rule("dotenv keys match case-insensitively")

(tmp / ".env3").write_text("APP_PORT=5\nUNRELATED=1\n")


class Forbid(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env3")
    port: int = 1


try:
    Forbid()
    raise AssertionError("expected extra_forbidden")
except ValidationError as err:
    assert "extra_forbidden" in str(err), err
    print("dotenv key no field names ->", str(err).splitlines()[1:3])


class Ignore(Forbid):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env3", extra="ignore")


assert Ignore().port == 5
rule(
    "a dotenv key matching no field (prefixed or not) fails construction (extra_forbidden) unless extra='ignore'; "
    "plain environment variables are never extra"
)

# 4. env_prefix_target (2.16): the prefix applies to aliases only when asked.
for target, alias_name in (("variable", "PORT_A"), ("alias", "APP_PORT_A"), ("all", "APP_PORT_A")):

    class T(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_", env_prefix_target=target)
        a: int = Field(1, alias="PORT_A")
        plain: int = 1

    os.environ[alias_name] = "9"
    os.environ["APP_PLAIN"] = "8"
    t = T()
    assert t.a == 9, (target, t.a)
    assert t.plain == (1 if target == "alias" else 8), (target, t.plain)
    clean()
rule(
    "env_prefix_target default 'variable': prefix on field-name variables only; 'alias': prefix on alias "
    "names only; 'all': both"
)

# 5. Source order and init kwargs.
src = inspect.getsource(BaseSettings.settings_customise_sources)
assert "return init_settings, env_settings, dotenv_settings, file_secret_settings" in src
os.environ["APP_PORT"] = "21"
assert Plain(port=99).port == 99
clean()
rule(
    "sources, highest first: init kwargs, environment, dotenv, secrets dir, then field default "
    "(settings_customise_sources returns init_settings, env_settings, dotenv_settings, file_secret_settings)"
)

print("OK")
