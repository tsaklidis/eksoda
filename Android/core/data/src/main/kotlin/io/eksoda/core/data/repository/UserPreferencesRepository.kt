package io.eksoda.core.data.repository

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
class UserPreferencesRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>
) {
    private val householdIdKey = stringPreferencesKey("selected_household_id")

    val selectedHouseholdId: Flow<String?> = dataStore.data.map { it[householdIdKey] }

    suspend fun getSelectedHouseholdId(): String? = selectedHouseholdId.first()

    suspend fun setHouseholdId(id: String) {
        dataStore.edit { preferences ->
            preferences[householdIdKey] = id
        }
    }

    suspend fun clear() {
        dataStore.edit { it.clear() }
    }
}
