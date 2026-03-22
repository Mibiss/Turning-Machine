package no.ainm.tripletex.agent

import kotlinx.serialization.json.JsonArray

data class TaskConfig(
    val taskType: TaskType,
    val systemPrompt: String,
    val tools: JsonArray,
    val toolsWithCache: JsonArray,
    val model: String = "claude-sonnet-4-6-20250514",
    val maxIterations: Int = 25,
)
