"""The settings file of the test tool (ruled 2026-11-26): pytest's, read so the resolve can
tell a settings module only the tests select (`DJANGO_SETTINGS_MODULE = app.settings_test`
under `[pytest]`) from one a deployment runs. Each setting written as one text is a config
entry; the document's language is `pytest`, which no config-model source matches, so no
`resolved_config` row comes from it.

**Claimed by NAME, never by suffix**, as a dotenv file is: `analyze` offers the files pytest
looks for at the module's root (`domain/resource_files.TEST_TOOL_SETTINGS`), in pytest's
order, and the first that holds pytest's settings is the one read
(`extract/python/pytest_collection.py`, the rules the scanner tells test code apart by)."""

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import ConfigEntryFact, Document, Fact
from sextant.domain.resource_files import TEST_TOOL_SETTINGS
from sextant.ingress.extract.python.pytest_collection import pytest_settings
from sextant.ingress.read import build_document

LANGUAGE = "pytest"


class PytestSettingsReader:
    reads_schema_sources = False

    def accepts(self, file_kind: str) -> bool:
        return file_kind in TEST_TOOL_SETTINGS

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        for file in request.files:
            settings = pytest_settings(file)
            if settings is None:
                continue
            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language=LANGUAGE,
                content=file.read_bytes(),
            )
            facts: list[Fact] = [
                ConfigEntryFact(
                    document_id=document.document_id,
                    key_raw=key,
                    key_path=key,
                    value=value.strip(),
                    doc_index=0,
                )
                for key, value in settings.items()
                if isinstance(value, str)
            ]
            return [(document, facts)]
        return []
