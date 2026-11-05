package com.acme.app

import okhttp3.OkHttpClient
import okhttp3.Request

class StatusCheck(private val client: OkHttpClient) {
    fun healthy(): Boolean {
        val request = Request.Builder().url("https://status.example.com/health").build()
        return client.newCall(request).execute().use { it.isSuccessful }
    }
}
