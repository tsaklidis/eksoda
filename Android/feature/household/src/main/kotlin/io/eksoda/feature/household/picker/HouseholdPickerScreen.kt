package io.eksoda.feature.household.picker

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import io.eksoda.core.designsystem.component.EksodaButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HouseholdPickerScreen(
    onNavigateToJoin: () -> Unit,
    viewModel: HouseholdPickerViewModel = hiltViewModel()
) {
    val uiState = viewModel.uiState
    var showJoinDialog by remember { mutableStateOf(false) }
    var inviteCode by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Select Household") })
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showJoinDialog = true }) {
                Icon(Icons.Default.Add, contentDescription = "Join Household")
            }
        }
    ) { padding ->
        if (uiState.isLoading && uiState.households.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (uiState.households.isEmpty() && !uiState.isLoading) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text("You are not a member of any household yet.")
                Spacer(modifier = Modifier.height(16.dp))
                EksodaButton(onClick = { showJoinDialog = true }, text = "Join with invite code")
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
            ) {
                items(uiState.households) { household ->
                    ListItem(
                        headlineContent = { Text(household.name) },
                        supportingContent = { Text(household.role.name) },
                        modifier = Modifier.clickable { viewModel.selectHousehold(household.id) }
                    )
                    HorizontalDivider()
                }
            }
        }
    }

    if (showJoinDialog) {
        AlertDialog(
            onDismissRequest = { showJoinDialog = false },
            title = { Text("Join Household") },
            text = {
                OutlinedTextField(
                    value = inviteCode,
                    onValueChange = { inviteCode = it },
                    label = { Text("Invite Code") },
                    modifier = Modifier.fillMaxWidth()
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.joinHousehold(inviteCode)
                        showJoinDialog = false
                    }
                ) {
                    Text("Join")
                }
            },
            dismissButton = {
                TextButton(onClick = { showJoinDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}
