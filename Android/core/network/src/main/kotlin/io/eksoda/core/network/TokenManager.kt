package io.eksoda.core.network

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TokenManager @Inject constructor(
    private val dataStore: DataStore<Preferences>
) {
    private val accessTokenKey = stringPreferencesKey("access_token")
    private val refreshTokenKey = stringPreferencesKey("refresh_token")

    suspend fun saveTokens(accessToken: String, refreshToken: String) {
        dataStore.edit { preferences ->
            preferences[accessTokenKey] = accessToken
            preferences[refreshTokenKey] = refreshToken
        }
    }

    suspend fun getAccessToken(): String? {
        return dataStore.data.map { it[accessTokenKey] }.first()
    }

    suspend fun getRefreshToken(): String? {
        return dataStore.data.map { it[refreshTokenKey] }.first()
    }

    fun getAccessTokenFlow(): Flow<String?> {
        return dataStore.data.map { it[accessTokenKey] }
    }

    suspend fun clearTokens() {
        dataStore.edit { it.clear() }
    }
}
