package no.ainm.tripletex.agent

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

object ToolDefinitions {

    // --- Individual tool definitions ---

    private val tripletexGet = buildJsonObject {
        put("name", "tripletex_get")
        put("description", "GET request to Tripletex API. Include query params in path like /customer?fields=id,name&count=100")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("path") {
                    put("type", "string")
                    put("description", "API path with query params, e.g. /employee?fields=id,firstName,lastName")
                }
            }
            putJsonArray("required") { add(kotlinx.serialization.json.JsonPrimitive("path")) }
        }
    }

    private val tripletexPost = buildJsonObject {
        put("name", "tripletex_post")
        put("description", "POST to create entity. Returns {\"value\":{\"id\":123,...}}. Use the returned ID directly.")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("path") {
                    put("type", "string")
                    put("description", "API path, e.g. /employee or /order/orderline")
                }
                putJsonObject("body") {
                    put("type", "string")
                    put("description", "JSON body as string")
                }
            }
            putJsonArray("required") {
                add(kotlinx.serialization.json.JsonPrimitive("path"))
                add(kotlinx.serialization.json.JsonPrimitive("body"))
            }
        }
    }

    private val tripletexPut = buildJsonObject {
        put("name", "tripletex_put")
        put("description", "PUT to update entity. Include ID in path. For action endpoints like /invoice/ID/:payment, put query params in the path and body can be empty or '{}'.")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("path") {
                    put("type", "string")
                    put("description", "API path with ID and optional query params, e.g. /employee/123 or /invoice/123/:payment?paymentDate=2026-01-01&paymentTypeId=456&paidAmount=1000")
                }
                putJsonObject("body") {
                    put("type", "string")
                    put("description", "JSON body as string. Can be '{}' for action endpoints that use query params.")
                }
            }
            putJsonArray("required") {
                add(kotlinx.serialization.json.JsonPrimitive("path"))
            }
        }
    }

    private val tripletexDelete = buildJsonObject {
        put("name", "tripletex_delete")
        put("description", "DELETE entity. Include ID in path.")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("path") {
                    put("type", "string")
                    put("description", "API path with ID, e.g. /travelExpense/123")
                }
            }
            putJsonArray("required") { add(kotlinx.serialization.json.JsonPrimitive("path")) }
        }
    }

    private val tripletexDocs = buildJsonObject {
        put("name", "tripletex_docs")
        put("description", "Look up Tripletex API documentation for an endpoint or topic. Use when you need to know the exact fields, parameters, or structure for an API endpoint you're unfamiliar with. Returns field definitions and usage examples.")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("query") {
                    put("type", "string")
                    put("description", "Endpoint path or topic to look up, e.g. '/employee/employment/details' or 'working hours' or 'salary transaction'")
                }
            }
            putJsonArray("required") { add(kotlinx.serialization.json.JsonPrimitive("query")) }
        }
    }

    private val calculateTool = buildJsonObject {
        put("name", "calculate")
        put("description", "Perform exact arithmetic for accounting calculations. ALWAYS use this instead of doing math yourself. Operations: depreciation, vat_gross_to_net, vat_net_to_gross, tax_provision, exchange_diff, sum.")
        putJsonObject("input_schema") {
            put("type", "object")
            putJsonObject("properties") {
                putJsonObject("operation") {
                    put("type", "string")
                    put("description", "One of: depreciation, vat_gross_to_net, vat_net_to_gross, tax_provision, exchange_diff, sum")
                    putJsonArray("enum") {
                        add(kotlinx.serialization.json.JsonPrimitive("depreciation"))
                        add(kotlinx.serialization.json.JsonPrimitive("vat_gross_to_net"))
                        add(kotlinx.serialization.json.JsonPrimitive("vat_net_to_gross"))
                        add(kotlinx.serialization.json.JsonPrimitive("tax_provision"))
                        add(kotlinx.serialization.json.JsonPrimitive("exchange_diff"))
                        add(kotlinx.serialization.json.JsonPrimitive("sum"))
                    }
                }
                putJsonObject("params") {
                    put("type", "object")
                    put("description", """Parameters depend on operation:
- depreciation: {"cost": number, "years": number, "is_monthly": boolean}
- vat_gross_to_net: {"amount": number, "vat_percent": number}
- vat_net_to_gross: {"amount": number, "vat_percent": number}
- tax_provision: {"revenue": number, "expenses": number}
- exchange_diff: {"amount": number, "invoice_rate": number, "payment_rate": number}
- sum: {"amounts": [number, number, ...]}""")
                }
            }
            putJsonArray("required") {
                add(kotlinx.serialization.json.JsonPrimitive("operation"))
                add(kotlinx.serialization.json.JsonPrimitive("params"))
            }
        }
    }

    // --- Tool subsets ---

    /** GET, POST, PUT, docs — most tasks */
    val readWriteTools: JsonArray = buildJsonArray {
        add(tripletexGet)
        add(tripletexPost)
        add(tripletexPut)
        add(tripletexDocs)
    }

    /** GET, POST, PUT, DELETE, docs — travel expense and similar */
    val readWriteDeleteTools: JsonArray = buildJsonArray {
        add(tripletexGet)
        add(tripletexPost)
        add(tripletexPut)
        add(tripletexDelete)
        add(tripletexDocs)
    }

    /** GET, POST, PUT, docs, calculate — tasks needing runtime math */
    val readWriteWithCalcTools: JsonArray = buildJsonArray {
        add(tripletexGet)
        add(tripletexPost)
        add(tripletexPut)
        add(tripletexDocs)
        add(calculateTool)
    }

    /** All tools: GET, POST, PUT, DELETE, docs, calculate */
    val allTools: JsonArray = buildJsonArray {
        add(tripletexGet)
        add(tripletexPost)
        add(tripletexPut)
        add(tripletexDelete)
        add(tripletexDocs)
        add(calculateTool)
    }

    // Legacy: full tool set without calculate (backward compat for GeneralPrompt)
    val tools: JsonArray = readWriteDeleteTools

    /** Adds cache_control to the last tool in the array for prompt caching. */
    fun withCache(tools: JsonArray): JsonArray = buildJsonArray {
        for ((index, tool) in tools.withIndex()) {
            if (index < tools.size - 1) {
                add(tool)
            } else {
                val toolObj = tool.jsonObject
                add(buildJsonObject {
                    toolObj.forEach { (key, value) -> put(key, value) }
                    putJsonObject("cache_control") { put("type", "ephemeral") }
                })
            }
        }
    }

    // Legacy: cached version of tools
    val toolsWithCache: JsonArray = withCache(tools)
}
