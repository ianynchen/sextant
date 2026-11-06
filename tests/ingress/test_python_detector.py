"""`PythonDetector` (spec 2026-11-06 §3e): the modules a repository holds, found from
its Python build files alone. Every tree is built in `tmp_path`; nothing is installed,
imported or run."""

from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.ingress.detect.python import PythonDetector


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
