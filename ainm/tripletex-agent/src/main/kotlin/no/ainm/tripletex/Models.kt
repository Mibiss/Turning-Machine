package no.ainm.tripletex

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class FileAttachment(
    val filename: String,
    @SerialName("content_base64") val contentBase64: String,
    @SerialName("mime_type") val mimeType: String,
)

@Serializable
data class TripletexCredentials(
    @SerialName("base_url") val baseUrl: String,
    @SerialName("session_token") val sessionToken: String,
)

@Serializable
data class SolveRequest(
    val prompt: String,
    val files: List<FileAttachment> = emptyList(),
    @SerialName("tripletex_credentials") val tripletexCredentials: TripletexCredentials,
)

@Serializable
data class SolveResponse(val status: String = "completed")
