package io.eksoda.core.ui.component

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.eksoda.core.model.Period
import java.time.format.DateTimeFormatter

@Composable
fun PeriodSelector(
    selectedPeriod: Period,
    onPeriodSelected: (Period) -> Unit,
    modifier: Modifier = Modifier
) {
    val dateFormatter = DateTimeFormatter.ofPattern("MMM d")
    
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = "${selectedPeriod.start.format(dateFormatter)} – ${selectedPeriod.end.format(dateFormatter)}",
                style = MaterialTheme.typography.titleSmall
            )
            TextButton(onClick = { /* TODO: Show Date Range Picker */ }) {
                Text("Change")
            }
        }
    }
}
