package no.ainm.tripletex

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import kotlinx.serialization.json.Json
import no.ainm.tripletex.agent.AccountingAgent
import java.net.InetSocketAddress

fun main() {
    val port = System.getenv("PORT")?.toIntOrNull() ?: 8080
    val apiKey = System.getenv("ANTHROPIC_API_KEY")
        ?: error("Set ANTHROPIC_API_KEY environment variable")
    val model = System.getenv("LLM_MODEL") ?: "claude-haiku-4-5-20251001"

    val json = Json { ignoreUnknownKeys = true }
    val server = HttpServer.create(InetSocketAddress(port), 0)

    val solveHandler = { exchange: HttpExchange ->
        TaskLogger.separator()
        TaskLogger.log(">> ${exchange.requestMethod} ${exchange.requestURI} from ${exchange.remoteAddress}")

        try {
            val body = exchange.requestBody.bufferedReader().readText()
            TaskLogger.log("   Body length: ${body.length}")
            val request = json.decodeFromString<SolveRequest>(body)

            TaskLogger.log("   Prompt (${request.prompt.length} chars): ${request.prompt.take(500)}")
            TaskLogger.log("   Files: ${request.files.size}, Base URL: ${request.tripletexCredentials.baseUrl}")

            val agent = AccountingAgent(apiKey = apiKey, model = model)
            agent.solve(request)

            TaskLogger.log("<< Task completed successfully")

            sendJson(exchange, 200, """{"status":"completed"}""")
        } catch (e: Exception) {
            TaskLogger.log("!! ERROR: ${e.javaClass.simpleName}: ${e.message}")
            e.printStackTrace(System.out)
            sendJson(exchange, 200, """{"status":"completed"}""")
        }
    }

    // Handle both /solve and root / in case competition posts to either
    server.createContext("/solve", solveHandler)
    server.createContext("/", solveHandler)

    server.executor = java.util.concurrent.Executors.newFixedThreadPool(5)
    server.start()
    TaskLogger.log("=== Tripletex Agent running on http://localhost:$port ===")
    TaskLogger.log("Expose with: npx cloudflared tunnel --url http://localhost:$port")
    TaskLogger.log("Then submit the HTTPS URL at https://app.ainm.no/submit/tripletex")
    TaskLogger.log("Logging to: logs/tripletex-log.txt")
}

private fun sendJson(exchange: HttpExchange, code: Int, body: String) {
    exchange.responseHeaders.add("Content-Type", "application/json")
    exchange.sendResponseHeaders(code, body.length.toLong())
    exchange.responseBody.write(body.toByteArray())
    exchange.responseBody.close()
}
