package no.ainm.tripletex.client

import okhttp3.OkHttpClient
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

object HttpClients {

    fun createTrustAll(
        connectTimeoutSecs: Long = 30,
        readTimeoutSecs: Long = 120,
        writeTimeoutSecs: Long = 30,
    ): OkHttpClient {
        val trustAll = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }

        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, arrayOf<TrustManager>(trustAll), java.security.SecureRandom())

        return OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAll)
            .hostnameVerifier { _, _ -> true }
            .connectTimeout(connectTimeoutSecs, TimeUnit.SECONDS)
            .readTimeout(readTimeoutSecs, TimeUnit.SECONDS)
            .writeTimeout(writeTimeoutSecs, TimeUnit.SECONDS)
            .build()
    }
}
