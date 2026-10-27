package probe

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.DefaultRequest
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.request.get

// Row group (l): the DefaultRequest plugin installed by `install(…)` rather than through
// `defaultRequest { }`, beside a plugin that sets no base. Its own file, so `ProbeKt`'s static
// initialiser (row 49) is unchanged; row 92 reads this file's configuration lambda.
val installedClient = HttpClient(CIO) {
    install(WebSockets)
    install(DefaultRequest) { url("https://installed.example.com/") }
}

suspend fun clientInstalledRelative() = installedClient.get("installed/path")
