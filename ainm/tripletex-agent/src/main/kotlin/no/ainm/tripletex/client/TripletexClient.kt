package no.ainm.tripletex.client

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Credentials
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class TripletexClient(
    private val baseUrl: String,
    sessionToken: String,
) {
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val authorization = Credentials.basic("0", sessionToken)
    private val http = HttpClients.createTrustAll(readTimeoutSecs = 60)

    fun get(path: String): ApiResponse {
        val request = Request.Builder()
            .url(buildUrl(path))
            .header("Authorization", authorization)
            .get()
            .build()

        return execute(request)
    }

    fun post(path: String, body: String): ApiResponse {
        val request = Request.Builder()
            .url(buildUrl(path))
            .header("Authorization", authorization)
            .post(body.toRequestBody(jsonMediaType))
            .build()

        return execute(request)
    }

    fun put(path: String, body: String): ApiResponse {
        val request = Request.Builder()
            .url(buildUrl(path))
            .header("Authorization", authorization)
            .put(body.toRequestBody(jsonMediaType))
            .build()

        return execute(request)
    }

    fun delete(path: String): ApiResponse {
        val request = Request.Builder()
            .url(buildUrl(path))
            .header("Authorization", authorization)
            .delete()
            .build()

        return execute(request)
    }

    private fun buildUrl(path: String): String {
        val raw = "${baseUrl.trimEnd('/')}/${path.trimStart('/')}"
        // Use OkHttp's HttpUrl to properly encode query parameters (handles å, spaces, etc.)
        val baseHttpUrl = raw.substringBefore('?').toHttpUrl()
        val queryString = raw.substringAfter('?', "")
        if (queryString.isEmpty()) return baseHttpUrl.toString()

        val builder = baseHttpUrl.newBuilder()
        queryString.split('&').forEach { param ->
            val key = param.substringBefore('=')
            val value = param.substringAfter('=', "")
            builder.addQueryParameter(key, value)
        }
        return builder.build().toString()
    }

    private fun execute(request: Request): ApiResponse {
        for (attempt in 1..3) {
            val response = http.newCall(request).execute().use { resp ->
                ApiResponse(
                    statusCode = resp.code,
                    body = resp.body?.string() ?: "",
                )
            }
            // Retry on 403 (transient proxy token issues), 429 (rate limit), and 500 (transient server errors)
            if (response.statusCode in listOf(403, 429, 500) && attempt < 3) {
                val waitMs = if (attempt == 1) 2000L else 5000L
                Thread.sleep(waitMs)
                continue
            }
            return response
        }
        // Should never reach here, but just in case
        return ApiResponse(statusCode = 500, body = "Retry exhausted")
    }
}

data class ApiResponse(val statusCode: Int, val body: String) {
    companion object {
        private val json = Json { ignoreUnknownKeys = true }
    }

    fun format(): String {
        if (statusCode !in 200..299) {
            val truncated = if (body.length > 3000) body.take(3000) + "\n...[truncated]" else body
            return "HTTP $statusCode\n$truncated"
        }

        // Try to compact large list responses
        if (body.length > 4000) {
            try {
                val root = json.parseToJsonElement(body).jsonObject
                val values = root["values"]?.jsonArray
                if (values != null && values.size > 5) {
                    val fullSize = root["fullResultSize"]?.jsonPrimitive?.int ?: values.size
                    val compacted = values.map { compactItem(it.jsonObject) }
                    return "HTTP $statusCode\n{\"fullResultSize\":$fullSize,\"count\":${values.size},\"values\":[\n${compacted.joinToString(",\n")}\n]}"
                }
            } catch (_: Exception) {
                // Not valid JSON or not a list - fall through to truncation
            }
        }

        val limit = 8000
        val truncated = if (body.length > limit) body.take(limit) + "\n...[truncated]" else body
        return "HTTP $statusCode\n$truncated"
    }

    /** Extract only essential fields from a JSON object, flattening nested objects to just id/number/name */
    private fun compactItem(obj: JsonObject): String {
        val parts = mutableListOf<String>()
        for ((key, value) in obj) {
            // Skip noisy fields
            if (key in setOf("url", "version", "versionDigest", "legalVatTypes", "ledgerType",
                    "balanceGroup", "vatLocked", "displayName", "changes", "isInactive",
                    "numberPretty", "description", "currency")) continue
            try {
                when {
                    value is JsonObject -> {
                        // Flatten nested objects to key fields only
                        val nested = value.jsonObject
                        val id = nested["id"]?.jsonPrimitive?.content
                        val number = nested["number"]?.jsonPrimitive?.content
                        val name = nested["name"]?.jsonPrimitive?.content
                        val compact = listOfNotNull(
                            id?.let { "\"id\":$it" },
                            number?.let { "\"number\":$it" },
                            name?.let { "\"name\":\"$it\"" }
                        ).joinToString(",")
                        if (compact.isNotEmpty()) parts.add("\"$key\":{$compact}")
                    }
                    else -> parts.add("\"$key\":$value")
                }
            } catch (_: Exception) {
                parts.add("\"$key\":$value")
            }
        }
        return "{${parts.joinToString(",")}}"
    }
}
