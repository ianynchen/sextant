"""`PythonDetector` (spec 2026-11-06 §3e): the modules a repository holds, found from
its Python build files alone. Every tree is built in `tmp_path`; nothing is installed,
imported or run."""

import os
from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.ingress.detect.python import PythonDetector, poetry_environment_name


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _environment(folder: Path, distributions: dict[str, str]) -> Path:
    """A virtual environment as `python -m venv` leaves it: `pyvenv.cfg`, and one
    `.dist-info/METADATA` per installed distribution under `site-packages`."""
    _write(folder / "pyvenv.cfg", "home = /usr/bin\n")
    site_packages = folder / "lib" / "python3.12" / "site-packages"
    for name, version in distributions.items():
        _write(
            site_packages / f"{name.replace('-', '_')}-{version}.dist-info" / "METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\nA long description.\n",
        )
    return site_packages


def _only_module(path: Path):
    modules = PythonDetector().detect(path).modules
    assert len(modules) == 1, modules
    return modules[0]


def test_pyproject_project_table_gives_name_and_version(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "Shop_Orders.API"\nversion = "1.4.0"\n'
        'dependencies = ["FastAPI[standard]>=0.110", "httpx"]\n',
    )
    _write(tmp_path / "shop_orders" / "__init__.py")

    module = _only_module(tmp_path)

    assert module.module_id == "shop-orders-api"
    assert module.coordinates == "shop-orders-api"
    assert module.version == "1.4.0"
    assert module.kind == "pyproject"
    assert module.root == tmp_path
    assert module.languages == frozenset({"python"})
    assert module.source_roots == (tmp_path,)
    assert module.output_dirs == ()
    assert module.packaging == "wheel"
    assert module.dependency_coordinates == ("fastapi", "httpx")


def test_poetry_table_is_read_when_project_table_is_absent(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[tool.poetry]\nname = "billing"\nversion = "2.0.1"\n'
        '[tool.poetry.dependencies]\npython = "^3.12"\nFlask = "^3.0"\n',
    )
    _write(tmp_path / "billing" / "__init__.py")

    module = _only_module(tmp_path)

    assert (module.module_id, module.version, module.kind) == ("billing", "2.0.1", "pyproject")
    assert module.dependency_coordinates == ("flask",)


def test_setup_cfg_metadata_gives_name_and_version(tmp_path: Path):
    _write(
        tmp_path / "setup.cfg",
        "[metadata]\nname = HTTPie\nversion = 3.2.4\n\n"
        "[options]\ninstall_requires =\n    requests[socks] >=2.22.0\n"
        '    colorama>=0.2.4; sys_platform=="win32"\n',
    )
    _write(tmp_path / "setup.py", "from setuptools import setup\nsetup()\n")
    _write(tmp_path / "httpie" / "__init__.py")

    module = _only_module(tmp_path)

    assert (module.module_id, module.version, module.kind) == ("httpie", "3.2.4", "setup_cfg")
    assert module.dependency_coordinates == ("colorama", "requests")


def test_setup_cfg_without_metadata_is_not_a_module(tmp_path: Path):
    """CTFd's `setup.cfg` holds only `[nosetests]`: test settings, not a project."""
    _write(tmp_path / "setup.cfg", "[nosetests]\nstop=1\nverbosity=2\n")
    _write(tmp_path / "app.py")

    assert not _has_any_module(tmp_path)


def _has_any_module(path: Path) -> bool:
    try:
        return bool(PythonDetector().detect(path).modules)
    except ValueError:
        return False


def test_setup_py_inside_a_package_is_not_a_module(tmp_path: Path):
    """CTFd's `CTFd/forms/setup.py` is a form named `setup`, inside a package."""
    _write(tmp_path / "requirements.txt", "flask\n")
    _write(tmp_path / "pkg" / "__init__.py")
    _write(tmp_path / "pkg" / "forms" / "__init__.py")
    _write(tmp_path / "pkg" / "forms" / "setup.py", "class SetupForm: ...\n")

    module = _only_module(tmp_path)

    assert module.root == tmp_path


def test_setup_py_inside_a_package_folder_without_its_own_init_is_not_a_module(tmp_path: Path):
    _write(tmp_path / "pkg" / "__init__.py")
    _write(tmp_path / "pkg" / "forms" / "setup.py", "class SetupForm: ...\n")

    assert not _has_any_module(tmp_path)


def test_setup_py_under_an_existing_module_is_not_a_module(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "server"\nversion = "0.0.0"\n')
    _write(tmp_path / "server" / "__init__.py")
    _write(tmp_path / "tools" / "collectors" / "setup.py", "def setup(): ...\n")

    module = _only_module(tmp_path)

    assert module.module_id == "server"


def test_requirements_only_service_is_an_unpublished_module(tmp_path: Path):
    service = tmp_path / "src" / "emailservice"
    _write(
        service / "requirements.txt", "# compiled\ngrpcio==1.62.0\n    # via -r in\nJinja2==3.1.4\n"
    )
    _write(service / "email_server.py")

    module = _only_module(tmp_path)

    assert module.coordinates == "."
    assert module.version == "."
    assert module.module_id == "src/emailservice"
    assert module.kind == "requirements"
    assert module.root == service
    assert module.dependency_coordinates == ("grpcio", "jinja2")


def test_requirements_file_with_no_python_beside_it_is_not_a_module(tmp_path: Path):
    _write(tmp_path / "docs" / "requirements.txt", "sphinx\n")
    _write(tmp_path / "svc" / "requirements.txt", "flask\n")
    _write(tmp_path / "svc" / "app.py")

    assert [m.module_id for m in PythonDetector().detect(tmp_path).modules] == ["svc"]


def test_uv_workspace_root_without_code_is_not_a_module_its_members_are(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[tool.uv.workspace]\nmembers = ["backend"]\n[dependency-groups]\ndev = ["typer"]\n',
    )
    _write(tmp_path / "backend" / "pyproject.toml", '[project]\nname = "app"\nversion = "0.1.0"\n')
    _write(tmp_path / "backend" / "app" / "main.py")
    site_packages = _environment(tmp_path / ".venv", {"app": "0.1.0"})

    module = _only_module(tmp_path)

    assert module.module_id == "app"
    assert module.root == tmp_path / "backend"
    # A uv workspace has one environment, at its root.
    assert module.environment == tmp_path / ".venv"
    assert site_packages.is_dir()


def test_uv_workspace_root_with_a_project_and_code_is_a_module_too(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "root"\nversion = "1.0"\n[tool.uv.workspace]\nmembers = ["libs/*"]\n',
    )
    _write(tmp_path / "root" / "__init__.py")
    _write(
        tmp_path / "libs" / "core" / "pyproject.toml", '[project]\nname = "core"\nversion = "1"\n'
    )
    _write(tmp_path / "libs" / "core" / "core" / "__init__.py")

    ids = sorted(m.module_id for m in PythonDetector().detect(tmp_path).modules)

    assert ids == ["core", "root"]


def test_dynamic_version_reads_installed_dist_info_else_dot(tmp_path: Path):
    installed = tmp_path / "installed"
    _write(installed / "pyproject.toml", '[project]\nname = "polar-sdk"\ndynamic = ["version"]\n')
    _write(installed / "polar" / "__init__.py")
    _environment(installed / ".venv", {"polar_sdk": "0.30.2"})
    not_installed = tmp_path / "not-installed"
    _write(
        not_installed / "setup.cfg",
        "[metadata]\nname = httpie\nversion = attr: httpie.__version__\n",
    )
    _write(not_installed / "httpie" / "__init__.py")

    assert _only_module(installed).version == "0.30.2"
    assert _only_module(not_installed).version == "."
    assert _only_module(not_installed).coordinates == "httpie"


def test_src_layout_import_root_is_src(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / "src" / "shop" / "__init__.py")
    _write(tmp_path / "tests" / "test_shop.py")

    assert _only_module(tmp_path).source_roots == (tmp_path / "src",)


def test_package_settings_name_the_import_root(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1"\n'
        '[tool.setuptools.packages.find]\nwhere = ["lib"]\n',
    )
    _write(tmp_path / "lib" / "shop" / "__init__.py")

    assert _only_module(tmp_path).source_roots == (tmp_path / "lib",)


def test_python_version_file_is_not_an_environment(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / ".python-version", "3.12\n")
    _write(tmp_path / "shop" / "__init__.py")

    module = _only_module(tmp_path)

    assert module.environment is None
    assert module.dependency_archives == ()


def test_folder_named_like_an_environment_without_pyvenv_cfg_is_not_one(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / "shop" / "__init__.py")
    _write(tmp_path / "venv" / "lib" / "python3.12" / "site-packages" / "x.py")

    assert _only_module(tmp_path).environment is None


def test_installed_distribution_versions_come_from_dist_info(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1"\ndependencies = ["fastapi", "Pydantic>=2", "absent"]\n',
    )
    _write(tmp_path / "shop" / "__init__.py")
    site_packages = _environment(
        tmp_path / "venv", {"fastapi": "0.115.0", "pydantic": "2.9.1", "starlette": "0.38.0"}
    )

    module = _only_module(tmp_path)

    assert module.environment == tmp_path / "venv"
    assert module.dependency_coordinates == ("absent", "fastapi", "pydantic")
    assert module.dependency_versions == {"fastapi": "0.115.0", "pydantic": "2.9.1"}
    assert module.dependency_archives == (
        LibraryRoot(coordinate="fastapi", version="0.115.0", archive=site_packages),
        LibraryRoot(coordinate="pydantic", version="2.9.1", archive=site_packages),
    )


def test_loose_py_folder_is_noted_not_analysed(tmp_path: Path):
    _write(tmp_path / "backend" / "pyproject.toml", '[project]\nname = "app"\nversion = "1"\n')
    _write(tmp_path / "backend" / "app" / "main.py")
    _write(tmp_path / "scripts" / "release.py")
    _write(tmp_path / "scripts" / "helpers" / "util.py")
    _write(tmp_path / "node_modules" / "pkg" / "build.py")

    model = PythonDetector().detect(tmp_path)

    assert [m.module_id for m in model.modules] == ["app"]
    assert model.notes == ("python files in a folder with no project file, not analysed: scripts",)


def test_sys_path_change_is_noted(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / "shop" / "__init__.py")
    _write(
        tmp_path / "manage.py",
        "import os\nimport sys\n\nsys.path.insert(0, os.path.dirname(__file__) + '/lib')\n",
    )

    model = PythonDetector().detect(tmp_path)

    assert model.notes == (
        (
            "manage.py:4: sys.path change, not followed: "
            "sys.path.insert(0, os.path.dirname(__file__) + '/lib')"
        ),
    )


def test_accepts_finds_a_build_file_at_any_depth(tmp_path: Path):
    _write(tmp_path / "services" / "orders" / "pyproject.toml", '[project]\nname = "o"\n')

    assert PythonDetector().accepts(tmp_path)


def test_accepts_skips_dependency_and_environment_folders(tmp_path: Path):
    _write(tmp_path / "node_modules" / "x" / "setup.py")
    _write(tmp_path / ".git" / "requirements.txt")
    _write(tmp_path / ".sextant" / "pyproject.toml")
    _write(tmp_path / "my-env" / "pyvenv.cfg")
    _write(tmp_path / "my-env" / "lib" / "python3.12" / "site-packages" / "p" / "setup.py")

    assert not PythonDetector().accepts(tmp_path)


def test_a_repository_with_no_module_is_refused_by_name(tmp_path: Path):
    _write(tmp_path / "setup.cfg", "[flake8]\nignore = E501\n")

    try:
        PythonDetector().detect(tmp_path)
    except ValueError as refused:
        assert "no Python module" in str(refused)
    else:
        raise AssertionError("expected a refusal")


# Fix round 1.


def test_root_requirements_without_code_does_not_swallow_the_services_under_it(tmp_path: Path):
    """The measured tree: a root lint list and two services, each with its own list."""
    _write(tmp_path / "requirements-dev.txt", "ruff\npytest\n")
    _write(tmp_path / "src" / "svc_a" / "requirements.txt", "flask\n")
    _write(tmp_path / "src" / "svc_a" / "app.py")
    _write(tmp_path / "src" / "svc_b" / "requirements.txt", "fastapi\n")
    _write(tmp_path / "src" / "svc_b" / "main.py")

    model = PythonDetector().detect(tmp_path)

    assert [m.module_id for m in model.modules] == ["src/svc_a", "src/svc_b"]
    assert model.notes == (
        "requirements with no python code of its own, not a module: requirements-dev.txt",
    )


def test_requirements_service_under_a_project_is_its_own_module(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / "shop" / "__init__.py")
    _write(tmp_path / "services" / "mailer" / "requirements.txt", "jinja2\n")
    _write(tmp_path / "services" / "mailer" / "server.py")

    ids = sorted(m.module_id for m in PythonDetector().detect(tmp_path).modules)

    assert ids == ["services/mailer", "shop"]


def test_unreadable_nested_build_file_is_a_note_and_the_rest_is_detected(tmp_path: Path):
    _write(tmp_path / "app" / "pyproject.toml", '[project]\nname = "app"\nversion = "1"\n')
    _write(tmp_path / "app" / "app" / "__init__.py")
    _write(tmp_path / "template" / "pyproject.toml", '[project]\nname = "{{ cookiecutter.name }}\n')
    _write(tmp_path / "template" / "main.py")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "setup.cfg").write_bytes(b"[metadata]\nname = caf\xe9\n")

    model = PythonDetector().detect(tmp_path)

    assert [m.module_id for m in model.modules] == ["app"]
    notes = "\n".join(model.notes)
    assert "build file not read, so its folder is not a module: template/pyproject.toml (" in notes
    assert "build file not read, so its folder is not a module: legacy/setup.cfg (" in notes


def test_unreadable_build_file_at_the_target_is_refused(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", "[project\n")
    _write(tmp_path / "app.py")

    try:
        PythonDetector().detect(tmp_path)
    except ValueError as refused:
        assert "pyproject.toml" in str(refused)
    else:
        raise AssertionError("expected a refusal")


def test_poetry_in_project_setting_names_dot_venv(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[tool.poetry]\nname = "billing"\nversion = "1"\n')
    _write(tmp_path / "poetry.toml", "[virtualenvs]\nin-project = true\n")
    _write(tmp_path / "billing" / "__init__.py")
    _environment(tmp_path / ".venv", {})

    assert _only_module(tmp_path).environment == tmp_path / ".venv"


def test_poetry_path_setting_names_the_folder_poetry_names(tmp_path: Path):
    project = tmp_path / "billing"
    _write(project / "pyproject.toml", '[tool.poetry]\nname = "Billing_API"\nversion = "1"\n')
    _write(project / "poetry.toml", '[virtualenvs]\npath = "../envs"\n')
    _write(project / "billing" / "__init__.py")
    name = poetry_environment_name("billing-api", project)
    _environment(tmp_path / "envs" / f"{name}-py3.12", {"flask": "3.0.0"})
    _environment(tmp_path / "envs" / "other-AAAAAAAA-py3.12", {})

    module = _only_module(project)

    assert module.environment == tmp_path / "envs" / f"{name}-py3.12"


def test_two_poetry_environments_for_one_project_are_not_chosen_between(tmp_path: Path):
    project = tmp_path / "billing"
    _write(project / "pyproject.toml", '[tool.poetry]\nname = "billing"\nversion = "1"\n')
    _write(project / "poetry.toml", '[virtualenvs]\npath = "../envs"\n')
    _write(project / "billing" / "__init__.py")
    name = poetry_environment_name("billing", project)
    _environment(tmp_path / "envs" / f"{name}-py3.11", {})
    _environment(tmp_path / "envs" / f"{name}-py3.12", {})

    model = PythonDetector().detect(project)

    assert model.modules[0].environment is None
    assert any(
        note.startswith("billing: more than one Poetry environment, none read: ")
        for note in model.notes
    )


def test_poetry_module_with_no_environment_is_noted(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[tool.poetry]\nname = "billing"\nversion = "1"\n')
    _write(tmp_path / "billing" / "__init__.py")

    model = PythonDetector().detect(tmp_path)

    assert model.modules[0].environment is None
    assert any(note.startswith("billing: no Poetry environment found") for note in model.notes)


def test_poetry_environment_name_is_poetrys_own():
    """Poetry's `EnvManager.generate_env_name`: the name, then the first 8 characters of
    the URL-safe base64 SHA-256 of the project folder's real path."""
    import base64
    import hashlib

    folder = Path("/work/billing")
    digest = hashlib.sha256(os.path.normcase(os.path.realpath(folder)).encode()).digest()
    expected = f"billing-{base64.urlsafe_b64encode(digest).decode()[:8]}"

    assert poetry_environment_name("billing", folder) == expected


def test_src_layout_module_is_python(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "shop"\nversion = "1"\n')
    _write(tmp_path / "src" / "shop" / "api" / "items.py")

    assert _only_module(tmp_path).languages == frozenset({"python"})


def test_uv_workspace_exclude_removes_a_member(tmp_path: Path):
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "root"\nversion = "1"\n'
        '[tool.uv.workspace]\nmembers = ["libs/*"]\nexclude = ["libs/old"]\n',
    )
    _write(tmp_path / "root" / "__init__.py")
    _environment(tmp_path / ".venv", {})
    for name in ("core", "old"):
        _write(tmp_path / "libs" / name / "pyproject.toml", f'[project]\nname = "{name}"\n')
        _write(tmp_path / "libs" / name / name / "__init__.py")

    by_id = {m.module_id: m for m in PythonDetector().detect(tmp_path).modules}

    assert by_id["core"].environment == tmp_path / ".venv"
    assert by_id["old"].environment is None
