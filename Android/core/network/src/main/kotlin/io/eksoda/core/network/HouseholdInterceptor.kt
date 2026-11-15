package io.eksoda.core.network

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HouseholdInterceptor @Inject constructor(
    private val dataStore: DataStore<Preferences>
) : Interceptor {
    private val householdIdKey = stringPreferencesKey("selected_household_id")

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        
        // Skip for auth endpoints
        val path = request.url.encodedPath
        if (path.contains("/auth/")) {
            return chain.proceed(request)
        }

        val householdId = runBlocking { 
            dataStore.data.map { it[householdIdKey] }.first()
        }

        val builder = request.newBuilder()
        if (householdId != null) {
            builder.header("X-Household-ID", householdId)
        }

        return chain.proceed(builder.build())
    }
}
