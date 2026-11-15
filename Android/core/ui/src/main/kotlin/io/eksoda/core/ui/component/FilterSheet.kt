package io.eksoda.core.ui.component

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.eksoda.core.model.ReceiptFilter
import io.eksoda.core.model.ReceiptOrdering

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptFilterSheet(
    filter: ReceiptFilter,
    onFilterChange: (ReceiptFilter) -> Unit,
    onDismiss: () -> Unit
) {
    var currentFilter by remember { mutableStateOf(filter) }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                text = "Filter Receipts",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            Text("Sort by", style = MaterialTheme.typography.labelLarge)
            Row(modifier = Modifier.padding(vertical = 8.dp)) {
                ReceiptOrdering.entries.forEach { ordering ->
                    FilterChip(
                        selected = currentFilter.ordering == ordering,
                        onClick = { currentFilter = currentFilter.copy(ordering = ordering) },
                        label = { Text(ordering.name.replace("_", " ").lowercase().capitalize()) },
                        modifier = Modifier.padding(end = 8.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            
            Text("Date Range", style = MaterialTheme.typography.labelLarge)
            Row(modifier = Modifier.padding(vertical = 8.dp)) {
                OutlinedButton(onClick = { /* TODO: Date Picker */ }) {
                    Text(currentFilter.issuedFrom?.toString() ?: "From")
                }
                Spacer(modifier = Modifier.width(8.dp))
                OutlinedButton(onClick = { /* TODO: Date Picker */ }) {
                    Text(currentFilter.issuedTo?.toString() ?: "To")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(
                    checked = currentFilter.isExcludedFromAnalytics == true,
                    onCheckedChange = { checked -> 
                        currentFilter = currentFilter.copy(isExcludedFromAnalytics = if (checked) true else null) 
                    }
                )
                Text("Excluded from analytics")
            }

            Spacer(modifier = Modifier.height(24.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = {
                    currentFilter = ReceiptFilter()
                }) {
                    Text("Clear All")
                }
                Spacer(modifier = Modifier.width(8.dp))
                Button(onClick = {
                    onFilterChange(currentFilter)
                    onDismiss()
                }) {
                    Text("Apply Filters")
                }
            }
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

private fun String.capitalize() = replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
