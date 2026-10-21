package com.acme.edge;

/**
 * The gateway module's one class. A real gateway always has at least this — the Boot
 * application class — and the fixture needs it for a reason that is not realism: git does not
 * track an empty directory, so a module with configuration and no source has NO source root in
 * a fresh checkout, and the detector then refuses it as having no language. The routes this
 * module exists to declare are in `application.yml`; this file is what makes CI able to see
 * them at all. MEASURED: the module analysed locally, where the empty directory existed, and
 * failed in CI, where it did not.
 */
public final class EdgeApplication {

    private EdgeApplication() {}
}
