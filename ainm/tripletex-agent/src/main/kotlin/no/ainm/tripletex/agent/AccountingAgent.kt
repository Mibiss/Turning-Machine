package no.ainm.tripletex.agent

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import no.ainm.tripletex.SolveRequest
import no.ainm.tripletex.TaskLogger
import no.ainm.tripletex.client.HttpClients
import no.ainm.tripletex.client.TripletexClient
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class AccountingAgent(
    private val apiKey: String,
    private val model: String = "claude-sonnet-4-6-20250514",
) {
    private val json = Json { ignoreUnknownKeys = true }
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val http = HttpClients.createTrustAll()
    private val scratchpad = Scratchpad()

    fun solve(request: SolveRequest) {
        val tripletex = TripletexClient(
            baseUrl = request.tripletexCredentials.baseUrl,
            sessionToken = request.tripletexCredentials.sessionToken,
        )

        // Step 1: Classify the task
        val taskType = TaskClassifier.classify(request.prompt, request.files)
        log("Classified task as: $taskType")

        // Step 2: Load task-specific config
        val config = TaskConfigRegistry.getConfig(taskType, model)
        log("Using prompt (${config.systemPrompt.length} chars), ${config.tools.size} tools, max ${config.maxIterations} iterations")

        // Step 3: Pre-compute calculations if needed
        val enrichedPrompt = CalculationInjector.inject(request.prompt, taskType)

        val messages = mutableListOf<JsonObject>()

        // Build initial user message
        val today = java.time.LocalDate.now().toString()
        messages.add(buildJsonObject {
            put("role", "user")
            putJsonArray("content") {
                // Add file attachments
                for (file in request.files) {
                    if (file.mimeType == "application/pdf") {
                        add(buildJsonObject {
                            put("type", "document")
                            putJsonObject("source") {
                                put("type", "base64")
                                put("media_type", "application/pdf")
                                put("data", file.contentBase64)
                            }
                        })
                    } else if (file.mimeType.startsWith("image/")) {
                        add(buildJsonObject {
                            put("type", "image")
                            putJsonObject("source") {
                                put("type", "base64")
                                put("media_type", file.mimeType)
                                put("data", file.contentBase64)
                            }
                        })
                    } else {
                        val decoded = try {
                            String(java.util.Base64.getDecoder().decode(file.contentBase64))
                        } catch (e: Exception) {
                            "[Could not decode file: ${file.filename}]"
                        }
                        add(buildJsonObject {
                            put("type", "text")
                            put("text", "[File: ${file.filename}]\n$decoded")
                        })
                    }
                }
                // Add the text prompt (possibly enriched with pre-computed values)
                val textContent = buildString {
                    if (request.files.isNotEmpty()) {
                        append("[Attached files: ${request.files.joinToString { it.filename }}]\n\n")
                    }
                    append(enrichedPrompt)
                    append("\n\n[Today's date: $today]")
                }
                add(buildJsonObject {
                    put("type", "text")
                    put("text", textContent)
                })
            }
        })

        // Agentic loop — uses task-specific config
        for (i in 0 until config.maxIterations) {
            log("--- Turn ${i + 1} ---")

            val response = try {
                callClaude(messages, config)
            } catch (e: Exception) {
                log("LLM call failed: ${e.message}")
                try {
                    log("Retrying...")
                    Thread.sleep(2000)
                    callClaude(messages, config)
                } catch (e2: Exception) {
                    log("Retry also failed: ${e2.message}, stopping.")
                    break
                }
            }

            val stopReason = response["stop_reason"]?.jsonPrimitive?.content
            val contentBlocks = response["content"]?.jsonArray
            if (contentBlocks == null) {
                log("ERROR: No content in response: ${response.toString().take(300)}")
                break
            }

            // Log any text blocks
            for (block in contentBlocks) {
                val blockObj = block.jsonObject
                if (blockObj["type"]?.jsonPrimitive?.content == "text") {
                    val text = blockObj["text"]?.jsonPrimitive?.content ?: ""
                    if (text.isNotBlank()) log("LLM: ${text.take(500)}")
                }
            }

            // Add assistant message to conversation
            messages.add(buildJsonObject {
                put("role", "assistant")
                put("content", contentBlocks)
            })

            // Check if we should stop
            if (stopReason != "tool_use") {
                log("Done (stop_reason=$stopReason)")
                break
            }

            // Execute tool calls and build tool results
            var tokenExpired = false
            val toolResults = buildJsonArray {
                for (block in contentBlocks) {
                    val blockObj = block.jsonObject
                    if (blockObj["type"]?.jsonPrimitive?.content != "tool_use") continue

                    val toolId = blockObj["id"]!!.jsonPrimitive.content
                    val name = blockObj["name"]!!.jsonPrimitive.content
                    val input = blockObj["input"]!!.jsonObject

                    val path = input["path"]?.jsonPrimitive?.content ?: ""
                    val query = input["query"]?.jsonPrimitive?.content ?: ""
                    val body = input["body"]?.jsonPrimitive?.content
                    if (name == "tripletex_docs") {
                        log("  CALL: $name query=$query")
                    } else if (name == "calculate") {
                        val operation = input["operation"]?.jsonPrimitive?.content ?: ""
                        log("  CALL: $name operation=$operation")
                    } else {
                        log("  CALL: $name $path${if (body != null) " body=${body.take(1500)}" else ""}")
                    }

                    val result = executeTool(tripletex, name, input)
                    log("  RESP: ${result.take(500)}")

                    // Extract key values into scratchpad for later turns
                    scratchpad.extract(result)

                    // Detect expired proxy token — abort immediately
                    if (result.contains("Invalid or expired proxy token")) {
                        log("FATAL: Proxy token expired, aborting task.")
                        tokenExpired = true
                    }

                    val reminderSuffix = scratchpad.reminder() ?: ""
                    add(buildJsonObject {
                        put("type", "tool_result")
                        put("tool_use_id", toolId)
                        put("content", result + reminderSuffix)
                    })
                }
            }

            if (tokenExpired) break

            // Add tool results as user message
            messages.add(buildJsonObject {
                put("role", "user")
                put("content", toolResults)
            })
        }
    }

    private fun log(msg: String) {
        TaskLogger.log("[Agent] $msg")
    }

    private fun executeTool(tripletex: TripletexClient, name: String, input: JsonObject): String {
        return try {
            if (name == "tripletex_docs") {
                val query = input["query"]!!.jsonPrimitive.content
                return TripletexDocs.search(query)
            }
            if (name == "calculate") {
                val operation = input["operation"]!!.jsonPrimitive.content
                val params = input["params"]!!.jsonObject
                // Convert JsonObject params to Map<String, Any>
                val paramsMap = params.entries.associate { (key, value) ->
                    key to when {
                        value is kotlinx.serialization.json.JsonArray -> value.map {
                            it.jsonPrimitive.content.toDoubleOrNull() ?: it.jsonPrimitive.content
                        }
                        value.jsonPrimitive.isString -> value.jsonPrimitive.content
                        value.jsonPrimitive.content == "true" -> true
                        value.jsonPrimitive.content == "false" -> false
                        else -> value.jsonPrimitive.content.toDoubleOrNull() ?: value.jsonPrimitive.content
                    }
                }
                return Calculators.execute(operation, paramsMap)
            }
            val path = input["path"]!!.jsonPrimitive.content
            when (name) {
                "tripletex_get" -> {
                    val response = tripletex.get(path)
                    val formatted = response.format()
                    // Auto-append posting summary for ledger/posting responses
                    if (path.contains("/ledger/posting") && response.statusCode in 200..299) {
                        val summary = PostingSummary.summarize(response.body)
                        if (summary != null) "$formatted$summary" else formatted
                    } else {
                        formatted
                    }
                }
                "tripletex_post" -> {
                    val body = input["body"]!!.jsonPrimitive.content
                    tripletex.post(path, body).format()
                }
                "tripletex_put" -> {
                    val body = input["body"]?.jsonPrimitive?.content ?: "{}"
                    tripletex.put(path, body).format()
                }
                "tripletex_delete" -> tripletex.delete(path).format()
                else -> "Error: Unknown tool '$name'"
            }
        } catch (e: Exception) {
            "Error executing $name: ${e.message}"
        }
    }

    private fun callClaude(messages: List<JsonObject>, config: TaskConfig): JsonObject {
        val requestBody = buildJsonObject {
            put("model", config.model)
            put("max_tokens", 4096)
            // Task-specific system prompt with cache_control
            putJsonArray("system") {
                add(buildJsonObject {
                    put("type", "text")
                    put("text", config.systemPrompt)
                    putJsonObject("cache_control") { put("type", "ephemeral") }
                })
            }
            putJsonArray("messages") {
                messages.forEach { add(it) }
            }
            put("tools", config.toolsWithCache)
        }

        for (attempt in 1..6) {
            val request = Request.Builder()
                .url("https://api.anthropic.com/v1/messages")
                .header("x-api-key", apiKey)
                .header("anthropic-version", "2023-06-01")
                .header("Content-Type", "application/json")
                .post(requestBody.toString().toRequestBody(jsonMediaType))
                .build()

            val resp = http.newCall(request).execute()
            val body = resp.body?.string() ?: throw RuntimeException("Empty Claude API response")

            if (resp.code == 429) {
                val waitSecs = when (attempt) { 1 -> 2L; 2 -> 3L; 3 -> 5L; else -> 8L }
                log("Rate limited, waiting ${waitSecs}s (attempt $attempt/6)...")
                Thread.sleep(waitSecs * 1000)
                continue
            }

            if (resp.code == 529) {
                val waitSecs = if (attempt <= 2) 5L else 10L
                log("API overloaded, waiting ${waitSecs}s (attempt $attempt/6)...")
                Thread.sleep(waitSecs * 1000)
                continue
            }

            if (!resp.isSuccessful) {
                throw RuntimeException("Claude API error ${resp.code}: ${body.take(500)}")
            }

            return json.decodeFromString<JsonObject>(body)
        }
        throw RuntimeException("Claude API failed after 6 retries")
    }
}
