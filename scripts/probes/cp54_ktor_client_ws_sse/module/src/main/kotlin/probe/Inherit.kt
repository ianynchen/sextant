package probe

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.get

// Row 80's shape as file-level code, for the real-bytecode check rather than a table row: a
// derived client with no `defaultRequest` of its own. Its own file, so `ProbeKt`'s static
// initialiser — which row 49 reads — is unchanged, and both clients are in THIS file's
// static initialiser, so `config`'s receiver is a `getstatic` of the parent.
val inheritParent = HttpClient(CIO) {
    defaultRequest { url("https://parent.example.com/p/") }
}

val inheritingClient = inheritParent.config { }

suspend fun clientInheritingRelative() = inheritingClient.get("inherited/path")
